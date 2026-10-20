import { sqliteTable, text, integer, uniqueIndex } from "drizzle-orm/sqlite-core";

export const jobs = sqliteTable("jobs", {
  id: text("id").primaryKey(),
  kind: text("kind").notNull(),
  input: text("input").notNull(),
  status: text("status").notNull(),
  stage: text("stage").notNull(),
  result: text("result"),
  error: text("error"),
  activeKey: text("active_key"),
  owner: text("owner"),
  leaseUntil: integer("lease_until").notNull().default(0),
  createdAt: integer("created_at").notNull(),
  updatedAt: integer("updated_at").notNull(),
}, (t) => [uniqueIndex("jobs_active_key_unique").on(t.activeKey)]);

export const workspaceState = sqliteTable("workspace_state", {
  key: text("key").primaryKey(),
  value: text("value").notNull(),
});
