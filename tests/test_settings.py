from __future__ import annotations

import json
import importlib.util
import io
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from engine import settings


PROJECT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
_WINDOWS_POWERSHELL = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
WINDOWS_POWERSHELL = str(_WINDOWS_POWERSHELL) if os.name == "nt" and _WINDOWS_POWERSHELL.is_file() else None


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workspace-settings-")
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "new project"
        self.project.mkdir()
        self.legacy = self.root / "old project"
        self.patches = [
            patch.object(settings, "ROOT", self.project),
            patch.dict(os.environ, {"OW_CONFIG": ""}),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def write_config(self, path, **extra):
        config = {
            "data_root": "data", "state_path": "data/state.json",
            "obsidian_vault": "vault", "output_root": "vault/知识工作台",
            "port": 18467, "web_port": 15174, **extra,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8-sig")
        return path

    def ready_config(self, path, **extra):
        self.write_config(path, **extra)
        (path.parent / "vault").mkdir()
        state = path.parent / "data/state.json"
        state.parent.mkdir()
        state.write_text(json.dumps({"version": 1, "files": {}, "threads": {}, "feishu": {},
                                     "baseline_at": "2026-10-01T00:00:00+00:00"}), encoding="utf-8")
        return path

    def test_new_machine_resolves_all_paths_relative_to_selected_config(self):
        path = self.write_config(self.root / "bundle/config.json",
            watch_roots=[{"name": "资料", "path": "../sources", "max_depth": 2}],
            memory_roots=["memory", {"name": "已提取记忆", "path": "../memory"}],
            old_output_roots=["vault/old"], generated_roots=["generated"],
            runtime_roots=["runtime"], allowed_open_roots=["vault"])
        result = settings.load_settings(path)
        self.assertEqual(str(path.parent / "data"), result["data_root"])
        self.assertEqual(str(self.root / "sources"), result["watch_roots"][0]["path"])
        self.assertEqual(2, result["watch_roots"][0]["max_depth"])
        self.assertEqual(str(path.parent / "memory"), result["memory_roots"][0])
        self.assertEqual(str(self.root / "memory"), result["memory_roots"][1]["path"])
        for key, child in (("old_output_roots", "vault/old"), ("generated_roots", "generated"),
                           ("runtime_roots", "runtime"), ("allowed_open_roots", "vault")):
            self.assertEqual(str(path.parent / child), result[key][0])
        self.assertEqual("", result["cloud_url"])
        self.assertFalse((path.parent / "data").exists())

    def test_explicit_then_project_then_environment_and_invalid_config_does_not_fall_back(self):
        explicit = self.write_config(self.root / "explicit.json", port=19001)
        local = self.write_config(self.project / "config.local.json", port=19002)
        environment = self.write_config(self.root / "environment.json", port=19003)
        os.environ["OW_CONFIG"] = str(environment)
        self.assertEqual(19001, settings.load_settings(explicit)["port"])
        self.assertEqual(19002, settings.load_settings()["port"])
        local.unlink()
        self.assertEqual(19003, settings.load_settings()["port"])
        with self.assertRaisesRegex(ValueError, "配置文件不存在"):
            settings.load_settings(self.root / "missing.json")
        local.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "JSON 无效"):
            settings.load_settings()

    def test_browser_selection_preserves_private_config_and_explicit_argument_wins(self):
        original = self.write_config(self.project / "config.local.json", port=19001)
        selected = self.write_config(self.root / "imported/workspace.json", port=19002)
        before = original.read_bytes()
        pointer = self.project / ".workspace-active.json"
        pointer.write_text(json.dumps({"config": str(selected)}), encoding="utf-8")
        self.assertEqual(19002, settings.load_settings()["port"])
        self.assertEqual("selected", settings.load_settings()["_config_source"])
        self.assertEqual(19001, settings.load_settings(original)["port"])
        self.assertEqual(before, original.read_bytes())
        selected.unlink()
        with self.assertRaisesRegex(ValueError, "配置文件不存在"):
            settings.load_settings()

    def test_bootstrap_empty_machine_reports_setup_without_initializing_checkpoint(self):
        with patch("sys.stdout", io.StringIO()) as output:
            self.assertEqual(0, settings.main(["--allow-setup", "--check-startup", "--api-port", "18701"]))
            result = json.loads(output.getvalue())
        self.assertTrue(result["setup_required"])
        self.assertEqual(18701, result["port"])
        self.assertFalse(Path(result["data_root"]).exists())
        self.assertFalse((self.project / "config.local.json").exists())
        with patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO()):
            self.assertEqual(2, settings.main(["--allow-setup", "--api-port", "0"]))

    def test_environment_paths_ports_and_new_source_defaults(self):
        os.environ["WORKSPACE_TEST_LOCATION"] = str(self.root / "portable")
        path = self.write_config(self.root / "config.json", data_root="%WORKSPACE_TEST_LOCATION%/data")
        result = settings.load_settings(path, api_port=19021, web_port=19022)
        self.assertEqual(str(self.root / "portable/data"), result["data_root"])
        self.assertEqual((19021, 19022), (result["port"], result["web_port"]))
        self.assertEqual([], result["watch_roots"])
        self.assertEqual([], result["memory_roots"])
        for bad in (0, 65536, True, "8767"):
            with self.subTest(port=bad), self.assertRaisesRegex(ValueError, "整数端口"):
                settings.load_settings(path, api_port=bad)
        with self.assertRaisesRegex(ValueError, "不能相同"):
            settings.load_settings(path, api_port=19021, web_port=19021)
        self.write_config(path, data_root="%WORKSPACE_UNDEFINED_LOCATION%/data")
        with self.assertRaisesRegex(ValueError, "未定义的环境变量"):
            settings.load_settings(path)

    def test_runtime_and_knowledge_directories_cannot_contain_each_other(self):
        path = self.root / "nested-config/config.json"
        for data_root, vault in (("vault/runtime", "vault"), ("data", "data/vault"), ("same", "same")):
            with self.subTest(data_root=data_root, vault=vault):
                self.write_config(path, data_root=data_root, obsidian_vault=vault,
                                  output_root=vault + "/30 资料")
                with self.assertRaisesRegex(ValueError, "必须互不包含"):
                    settings.load_settings(path)
                self.assertFalse((path.parent / data_root).exists())
                self.assertFalse((path.parent / vault).exists())

    def test_no_config_or_checkpoint_is_never_initialized(self):
        with self.assertRaisesRegex(ValueError, "未找到配置"):
            settings.load_settings()
        path = self.write_config(self.root / "config.json")
        config = settings.load_settings(path)
        with self.assertRaisesRegex(ValueError, "检查点不存在"):
            settings.validate_startup(config)
        self.assertFalse(Path(config["state_path"]).exists())
        self.assertFalse(Path(config["data_root"]).exists())

    def test_service_configuration_uses_selected_config_without_echoing_token(self):
        spec = importlib.util.spec_from_file_location("configure_service", PROJECT / "configure-service.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        path = self.write_config(self.root / "service/config.json")
        with patch.object(module, "save_service_token") as save, patch.object(module.sys, "stdin", io.StringIO(
                json.dumps({"token": "synthetic-private-value", "config": str(self.root / "wrong.json")}) + "\n")), \
                patch.object(module.sys, "stdout", io.StringIO()) as output:
            self.assertEqual(0, module.main(["--config", str(path)]))
            save.assert_called_once_with(path.parent / "data/service-token.dpapi", "synthetic-private-value")
            self.assertNotIn("synthetic-private-value", output.getvalue())
        with patch.object(module, "save_service_token") as save, \
                patch.object(module.sys, "stdin", io.StringIO('{"token":""}\n')), \
                patch.object(module.sys, "stdout", io.StringIO()), \
                patch.object(module.sys, "stderr", io.StringIO()) as error:
            self.assertEqual(2, module.main(["--config", str(path)]))
            save.assert_not_called()
            self.assertIn("非空 token", error.getvalue())

    def test_legacy_files_do_not_implicitly_select_a_workspace(self):
        self.legacy.mkdir()
        (self.legacy / "config.json").write_text('{"obsidian_vault":"old-vault"}', encoding="utf-8")
        (self.legacy / "config.local.json").write_text('{}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "未找到配置"):
            settings.load_settings()
        self.assertFalse((self.project / "config.local.json").exists())

    @unittest.skipUnless(os.name == "nt" and POWERSHELL and shutil.which("py"), "Windows launcher")
    def test_isolated_bootstrap_launcher_opens_setup_without_a_config_or_checkpoint(self):
        (self.project / "engine").mkdir()
        for name in ("settings.py", "incremental.py"):
            shutil.copy2(PROJECT / "engine" / name, self.project / "engine" / name)
        shutil.copy2(PROJECT / "start.ps1", self.project / "start.ps1")
        checked = subprocess.run([POWERSHELL, "-NoProfile", "-File", str(self.project / "start.ps1"),
                                  "-Bootstrap", "-Check", "-ApiPort", "18703", "-WebPort", "18704"],
                                 cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(0, checked.returncode, checked.stderr)
        result = json.loads(checked.stdout)
        self.assertTrue(result["setup_required"])
        self.assertEqual((18703, 18704), (result["port"], result["web_port"]))
        self.assertFalse((self.project / ".migration-staging").exists())

    @unittest.skipUnless(os.name == "nt" and POWERSHELL and shutil.which("py"), "Windows launcher")
    def test_launcher_check_reads_relative_config_and_explicit_port_overrides_without_starting(self):
        path = self.ready_config(self.root / "bundle/config.json")
        command = [POWERSHELL, "-NoProfile", "-File", str(PROJECT / "start.ps1"),
                   "-Config", "bundle/config.json", "-Check"]
        checked = subprocess.run(command, cwd=self.root, capture_output=True, text=True,
                                 encoding="utf-8", timeout=30)
        self.assertEqual(0, checked.returncode, checked.stderr)
        result = json.loads(checked.stdout)
        self.assertEqual((18467, 15174), (result["port"], result["web_port"]))
        self.assertEqual(str(path), result["config_path"])
        override = subprocess.run(command + ["-ApiPort", "19031", "-WebPort", "19032"],
                                  cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(0, override.returncode, override.stderr)
        result = json.loads(override.stdout)
        self.assertEqual((19031, 19032), (result["port"], result["web_port"]))
        self.assertFalse((path.parent / "data/logs").exists())

    @unittest.skipUnless(WINDOWS_POWERSHELL and shutil.which("py") and shutil.which("node"),
                         "Windows PowerShell 5.1 launcher integration")
    def test_launcher_ports_reach_isolated_api_and_web_processes(self):
        version = subprocess.run([WINDOWS_POWERSHELL, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.Major"],
                                 capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertEqual(version.stdout.strip(), "5", "The .cmd launcher uses Windows PowerShell 5.1, not pwsh")
        ports = []
        for _ in range(2):
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                ports.append(probe.getsockname()[1])
        if ports[0] == ports[1]:
            self.skipTest("Ephemeral ports were reused")
        (self.project / "engine").mkdir()
        for name in ("settings.py", "incremental.py"):
            shutil.copy2(PROJECT / "engine" / name, self.project / "engine" / name)
        shutil.copy2(PROJECT / "start.ps1", self.project / "start.ps1")
        shutil.copy2(PROJECT / "stop.ps1", self.project / "stop.ps1")
        web = self.project / "web"
        (web / "node_modules/vinext/dist").mkdir(parents=True)
        (web / "node_modules/vinext/dist/cli.js").write_text("", encoding="utf-8")
        (web / "scripts").mkdir()
        (self.project / "server.py").write_text('''import argparse,json,os
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
p=argparse.ArgumentParser();p.add_argument("--port",type=int);p.add_argument("--config");p.add_argument("--web-port",type=int);p.add_argument("--allow-setup",action="store_true");a=p.parse_args()
Path("api.pid").write_text(str(os.getpid()))
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
  self.wfile.write(json.dumps({"mode":"local","worker_running":True,"runtime_id":"synthetic-runtime-"+str(os.getpid()),"active_job":"synthetic-job" if Path("active.flag").exists() else None,"migration_switching":Path("migration.flag").exists(),"fixture_port":a.port,"fixture_config":a.config}).encode())
 def log_message(self,*args):pass
HTTPServer(("127.0.0.1",a.port),Handler).serve_forever()
''', encoding="utf-8")
        (web / "scripts/run-framework.mjs").write_text('''import fs from "node:fs";import http from "node:http";
fs.writeFileSync("../web.pid",String(process.pid));
const port=Number(process.argv[process.argv.indexOf("--port")+1]);
const target=fs.readFileSync(".dev.vars","utf8").match(/OW_LOCAL_API="([^"]+)"/)[1];
http.createServer(async(req,res)=>{try {const r=await fetch(target+req.url);const body=await r.json();if(fs.existsSync("../foreign.flag"))body.runtime_id="another-runtime";res.writeHead(r.status,{"Content-Type":"application/json"});res.end(JSON.stringify(body));} catch {res.writeHead(503);res.end("{}");}}).listen(port,"127.0.0.1");
''', encoding="utf-8")
        config = self.ready_config(self.root / "actual configuration/config.json")
        record = {}
        try:
            launch_command = [WINDOWS_POWERSHELL, "-NoProfile", "-File", str(self.project / "start.ps1"),
                              "-Config", str(config), "-ApiPort", str(ports[0]), "-WebPort", str(ports[1])]
            dev_vars = web / ".dev.vars"
            dev_vars.write_text('OW_LOCAL_API="http://127.0.0.1:1"\n', encoding="utf-8")
            conflict = subprocess.run(launch_command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertNotEqual(0, conflict.returncode)
            self.assertIn("独立源码副本", conflict.stderr)
            self.assertIn(":1", dev_vars.read_text())
            self.assertFalse((self.project / "api.pid").exists())
            dev_vars.unlink()
            with socket.socket() as occupied_web:
                occupied_web.bind(("127.0.0.1", ports[1]))
                occupied_web.listen()
                conflict = subprocess.run(launch_command, capture_output=True, text=True, encoding="utf-8", timeout=30)
                self.assertNotEqual(0, conflict.returncode)
                self.assertIn("未启动 API", conflict.stderr)
                self.assertFalse((self.project / "api.pid").exists())
            launch_log = self.root / "launcher.log"
            with launch_log.open("w", encoding="utf-8") as output:
                run = subprocess.run(launch_command, cwd=self.root, stdout=output, stderr=subprocess.STDOUT, timeout=45)
            self.assertEqual(0, run.returncode, launch_log.read_text(encoding="utf-8"))
            for port in ports:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/workspace/health", timeout=3) as response:
                    health = json.load(response)
                self.assertEqual(ports[0], health["fixture_port"])
                self.assertEqual(str(config), health["fixture_config"])
            record = json.loads((config.parent / "data/logs/last-start.json").read_text(encoding="utf-8-sig"))
            self.assertEqual((ports[0], ports[1]), (record["api_port"], record["web_port"]))
            stop_command = [WINDOWS_POWERSHELL, "-NoProfile", "-File", str(self.project / "stop.ps1"),
                            "-Config", str(config), "-ApiPort", str(ports[0])]
            (self.project / "active.flag").touch()
            active = subprocess.run(stop_command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertNotEqual(0, active.returncode)
            self.assertIn("synthetic-job", active.stderr)
            (self.project / "active.flag").unlink()
            (self.project / "migration.flag").touch()
            migrating = subprocess.run(stop_command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertNotEqual(0, migrating.returncode)
            self.assertIn("迁移", migrating.stderr)
            with urllib.request.urlopen(f"http://127.0.0.1:{ports[0]}/api/workspace/health", timeout=3) as response:
                migration_health = json.load(response)
            self.assertTrue(migration_health["migration_switching"])
            self.assertIsNone(migration_health["active_job"])
            (self.project / "migration.flag").unlink()
            wrong = self.write_config(self.root / "wrong config.json")
            mismatch = subprocess.run(stop_command[:-3] + [str(wrong), "-ApiPort", str(ports[0])],
                                      capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertNotEqual(0, mismatch.returncode)
            self.assertIn("其他配置", mismatch.stderr)
            api_pid = int((self.project / "api.pid").read_text())
            # Before this upgrade, reusing the webpage stored a null PID. Stop
            # must verify its live proxy and repair that record before stopping.
            legacy_record = {**record, "web_pid": None}
            legacy_record.pop("project_root", None)
            record_path = config.parent / "data/logs/last-start.json"
            record_path.write_text(json.dumps(legacy_record), encoding="utf-8")
            for lock in ("executor.lock", "state.lock"):
                (config.parent / "data" / lock).write_text(json.dumps({"pid": api_pid}), encoding="utf-8")
            stopped = subprocess.run(stop_command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(0, stopped.returncode, stopped.stderr)
            verified_record = json.loads(record_path.read_text(encoding="utf-8-sig"))
            self.assertEqual(int((self.project / "web.pid").read_text()), verified_record["web_pid"])
            self.assertEqual(str(self.project), verified_record["project_root"])
            self.assertFalse((config.parent / "data/executor.lock").exists())
            self.assertFalse((config.parent / "data/state.lock").exists())
            with self.assertRaises(OSError):
                urllib.request.urlopen(f"http://127.0.0.1:{ports[0]}/api/workspace/health", timeout=2)
            # An unrelated active writer's marker must survive even after the API is stopped.
            lock = config.parent / "data/state.lock"
            lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
            guarded = subprocess.run(stop_command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertNotEqual(0, guarded.returncode)
            self.assertEqual(os.getpid(), json.loads(lock.read_text())["pid"])
            lock.unlink()
            original_web_pid = int((self.project / "web.pid").read_text())
            with launch_log.open("w", encoding="utf-8") as output:
                restarted = subprocess.run(launch_command, cwd=self.root, stdout=output,
                                           stderr=subprocess.STDOUT, timeout=45)
            self.assertEqual(0, restarted.returncode, launch_log.read_text(encoding="utf-8"))
            record = json.loads((config.parent / "data/logs/last-start.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(original_web_pid, record["web_pid"])
            with urllib.request.urlopen(f"http://127.0.0.1:{ports[1]}/api/workspace/health", timeout=3) as response:
                self.assertEqual(str(config), json.load(response)["fixture_config"])
            # A node webpage on the expected port is insufficient: a different
            # runtime must never be registered as this checkout's reusable UI.
            (self.project / "foreign.flag").touch()
            record_path.write_text(json.dumps({**record, "web_pid": None}), encoding="utf-8")
            foreign = subprocess.run(stop_command, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(0, foreign.returncode, foreign.stderr)
            self.assertIn("网页归属未核实", foreign.stdout)
            self.assertIsNone(json.loads(record_path.read_text(encoding="utf-8-sig"))["web_pid"])
        finally:
            fixture_pids = []
            for name in ("api.pid", "web.pid"):
                pid_file = self.project / name
                if pid_file.is_file():
                    fixture_pids.append(int(pid_file.read_text()))
            if record.get("api_pid"):
                fixture_pids.append(int(record["api_pid"]))
            if fixture_pids:
                ids = ",".join(str(pid) for pid in fixture_pids)
                subprocess.run([POWERSHELL, "-NoProfile", "-Command",
                                f"$ids=@({ids}); Stop-Process -Id $ids -ErrorAction SilentlyContinue; "
                                "Wait-Process -Id $ids -Timeout 10 -ErrorAction SilentlyContinue"],
                               capture_output=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
