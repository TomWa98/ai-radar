import { describe, expect, it } from "vitest";
import css from "./tokens.css?raw";

// Guards the design decisions on color contrast (docs/frontend-design.md 2.1).

function token(name: string): string {
  const match = new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`).exec(css);
  if (!match?.[1]) {
    throw new Error(`Missing color token --${name}`);
  }
  return match[1];
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const SURFACES = ["color-bg", "color-surface", "color-surface-hover"];

describe("design tokens", () => {
  it("keep the specified palette", () => {
    expect(token("color-bg")).toBe("#0c0d10");
    expect(token("color-surface")).toBe("#1c1f24");
    expect(token("color-accent")).toBe("#d5d9df");
  });

  it.each(["color-text-primary", "color-text-secondary"])(
    "%s meets WCAG AA (4.5:1) on all surfaces",
    (text) => {
      for (const surface of SURFACES) {
        expect(contrast(token(text), token(surface))).toBeGreaterThanOrEqual(4.5);
      }
    },
  );

  it.each(["color-border-interactive", "color-focus"])(
    "%s meets WCAG 1.4.11 (3:1) on all surfaces",
    (boundary) => {
      for (const surface of SURFACES) {
        expect(contrast(token(boundary), token(surface))).toBeGreaterThanOrEqual(3);
      }
    },
  );

  it("uses a system font stack without font files", () => {
    expect(css).toMatch(/--font-family:\s*Inter, Geist, system-ui/);
    expect(css).not.toMatch(/@font-face|url\(/);
  });
});
