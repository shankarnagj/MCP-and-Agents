import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SignalTag, StatusBadge } from "../../src/components/ui";

describe("epistemic UI", () => {
  it("labels system inferences distinctly from facts", () => {
    render(<><StatusBadge status="SYSTEM_INFERENCE" /><StatusBadge status="ANALYST_ASSERTION" /><StatusBadge status="VERIFIED" /></>);
    expect(screen.getByText("INFERENCE")).toHaveAttribute("title", expect.stringContaining("not an established fact"));
    expect(screen.getByText("ASSERTION")).toHaveAttribute("title", expect.stringContaining("hypothesis"));
    expect(screen.getByText("VERIFIED")).toBeInTheDocument();
  });
  it("signals are labelled ANALYTICAL SIGNAL, never a verdict", () => {
    render(<SignalTag />);
    expect(screen.getByText("ANALYTICAL SIGNAL")).toBeInTheDocument();
  });
});

describe("no verdict language in UI source", () => {
  it("does not contain accusatory labels", async () => {
    const files = import.meta.glob("../../src/**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
    const bad = /\b(is|are) (fraudulent|guilty|criminal|a fraudster|malicious)\b/i;
    for (const [path, src] of Object.entries(files)) expect(bad.test(src), path).toBe(false);
  });
});
