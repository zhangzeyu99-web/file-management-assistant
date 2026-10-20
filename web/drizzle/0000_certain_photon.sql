CREATE TABLE `jobs` (
	`id` text PRIMARY KEY NOT NULL,
	`kind` text NOT NULL,
	`input` text NOT NULL,
	`status` text NOT NULL,
	`stage` text NOT NULL,
	`result` text,
	`error` text,
	`active_key` text,
	`owner` text,
	`lease_until` integer DEFAULT 0 NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `jobs_active_key_unique` ON `jobs` (`active_key`);--> statement-breakpoint
CREATE TABLE `workspace_state` (
	`key` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL
);
