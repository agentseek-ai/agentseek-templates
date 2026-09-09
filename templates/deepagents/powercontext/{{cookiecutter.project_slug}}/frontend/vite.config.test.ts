import { describe, expect, it } from "vitest";
import type { UserConfig } from "vite";
import viteConfig from "./vite.config.ts";

const config = viteConfig as UserConfig;

describe("vite server binding", () => {
  it("binds the dev server to the lifecycle health-check address", () => {
    expect(config.server?.host).toBe("127.0.0.1");
  });
});
