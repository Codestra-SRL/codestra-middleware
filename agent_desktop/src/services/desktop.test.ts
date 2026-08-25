import {afterEach,describe,expect,it,vi} from "vitest";
import {liveDesktopService} from "./desktop";

describe("liveDesktopService (AGENT-01: real, non-mocked persistence)",()=>{
  afterEach(()=>{vi.unstubAllGlobals();});

  it("posts disposition to the middleware with idempotency and correlation headers",async()=>{
    const fetchMock=vi.fn().mockResolvedValue(new Response(JSON.stringify({status:"accepted"}),{status:202}));
    vi.stubGlobal("fetch",fetchMock);
    await liveDesktopService.disposition("SYN-9001","QUALIFIED","call-123");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url,init]=fetchMock.mock.calls[0] as [string,RequestInit];
    expect(url).toBe("/api/v1/interactions/call-123/disposition");
    expect(init.credentials).toBe("include");
    const headers=init.headers as Record<string,string>;
    expect(headers["Idempotency-Key"]).toBeTruthy();
    expect(headers["X-Correlation-ID"]).toBeTruthy();
    expect(JSON.parse(String(init.body))).toEqual({crm_lead_public_id:"SYN-9001",disposition_code:"QUALIFIED"});
  });

  it("throws on a non-ok response instead of silently succeeding", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("server error", {status: 500})));
    await expect(liveDesktopService.saveNotes("SYN-9001", "note text", "call-123")).rejects.toThrow(/500/);
  });

  it("falls back to a lead-scoped interaction id when no active call is known",async()=>{
    const fetchMock=vi.fn().mockResolvedValue(new Response(JSON.stringify({status:"accepted"}),{status:202}));
    vi.stubGlobal("fetch",fetchMock);
    await liveDesktopService.saveNotes("SYN-9001","note text");
    const [url]=fetchMock.mock.calls[0] as [string];
    expect(url).toBe("/api/v1/interactions/no-active-call%3ASYN-9001/notes");
  });

  it("reuses the same idempotency key when retrying the identical save (timeout/double-click safe)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({status: "accepted"}), {status: 202}));
    vi.stubGlobal("fetch", fetchMock);
    await liveDesktopService.disposition("SYN-9001", "QUALIFIED", "call-123");
    await liveDesktopService.disposition("SYN-9001", "QUALIFIED", "call-123");
    const key1 = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    const key2 = (fetchMock.mock.calls[1][1] as RequestInit).headers as Record<string, string>;
    expect(key1["Idempotency-Key"]).toBe(key2["Idempotency-Key"]);
    // Correlation ID still varies per attempt -- it's per-request tracing, not the dedup key.
    expect(key1["X-Correlation-ID"]).not.toBe(key2["X-Correlation-ID"]);
  });

  it("uses a different idempotency key when the content of the save actually changes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({status: "accepted"}), {status: 202}));
    vi.stubGlobal("fetch", fetchMock);
    await liveDesktopService.disposition("SYN-9001", "QUALIFIED", "call-123");
    await liveDesktopService.disposition("SYN-9001", "NOT_INTERESTED", "call-123");
    const key1 = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    const key2 = (fetchMock.mock.calls[1][1] as RequestInit).headers as Record<string, string>;
    expect(key1["Idempotency-Key"]).not.toBe(key2["Idempotency-Key"]);
  });
});
