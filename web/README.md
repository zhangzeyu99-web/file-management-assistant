# 知识工作台网页

本目录是实际的阅读、检索、接续、收录、任务和迁移界面。使用 React、TypeScript、vinext；本机代理 Python API，线上通过 Sites 的登录保护、D1 队列和 R2 知识快照工作。

## 本机开发

优先从仓库根目录运行 `start.ps1 -Config <自己的配置>`，由它校验资料库、准备本机 API 绑定并启动网页。首次使用见根 README；不要在本目录初始化知识库。

需要单独启动网页时：

```powershell
npm run install:ci
npm run dev -- --port 5174 --hostname 127.0.0.1
```

本机 API 地址由忽略的 `.dev.vars` 中 `OW_LOCAL_API` 指定，仅接受 loopback；不要把该文件带到线上。

## 验证

```powershell
node --experimental-strip-types --test tests/*.test.mjs
npx tsc --noEmit
npm run build
```

## 线上数据

`db/schema.ts` 定义 `jobs` 与 `workspace_state`，实际迁移在 `drizzle/`。线上绑定为 `DB` 和 `BUCKET`，API 位于 `app/api/workspace/[...path]/route.ts`。所有线上请求依赖平台访问控制，不作为无认证公网 API 运行。完整部署方法见 `../docs/DEPLOYMENT.md`。

`build/`、安装脚本及 connector preview 是平台运行基础设施，不能当作业务演示删除。公开源码不包含站点 ID、授权或用户数据；部署工作副本位于自己的忽略目录。
