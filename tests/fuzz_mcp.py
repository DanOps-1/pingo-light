#!/usr/bin/env python3
"""
MCP Server Fuzzer for bingo-light mcp-server.py

Tests type injection, missing fields, oversized payloads,
boundary values, and protocol-level attacks.
"""

import json
import os
import subprocess
import sys
import time
import signal
import shutil
import struct
import threading

# ─── Config ──────────────────────────────────────────────────────────────────

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP_SERVER = os.path.join(_REPO_ROOT, "mcp-server.py")
BINGO_LIGHT = os.path.join(_REPO_ROOT, "bingo-light")
TEST_REPO = "/tmp/mcp-fuzz"
TIMEOUT = 5  # seconds per test

# ─── Helpers ─────────────────────────────────────────────────────────────────

class MCPClient:
    """Manages a single MCP server process and provides send/recv."""

    def __init__(self):
        self.proc = None

    def start(self):
        env = os.environ.copy()
        env["BINGO_LIGHT_BIN"] = BINGO_LIGHT
        self.proc = subprocess.Popen(
            [sys.executable, MCP_SERVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.close()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    def send_raw(self, data: bytes):
        """Send raw bytes to stdin."""
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def send_message(self, msg: dict):
        """Send a properly framed MCP message."""
        body = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        self.send_raw(header + body)

    def recv_message(self, timeout=TIMEOUT) -> dict | None:
        """Read one MCP response. Returns None on timeout."""
        result = [None]
        error = [None]

        def _read():
            try:
                # Read headers
                headers = {}
                while True:
                    line = self.proc.stdout.readline()
                    if not line:
                        error[0] = "EOF"
                        return
                    line = line.decode("utf-8", errors="replace").strip()
                    if line == "":
                        break
                    if ":" in line:
                        key, value = line.split(":", 1)
                        headers[key.strip().lower()] = value.strip()

                content_length = int(headers.get("content-length", 0))
                if content_length == 0:
                    error[0] = "No content-length"
                    return

                body = self.proc.stdout.read(content_length)
                result[0] = json.loads(body.decode("utf-8"))
            except Exception as e:
                error[0] = str(e)

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            return "TIMEOUT"
        if error[0]:
            return f"ERROR:{error[0]}"
        return result[0]

    def initialize(self):
        """Perform the MCP initialize handshake."""
        self.send_message({
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "fuzzer", "version": "0.1"}
            }
        })
        resp = self.recv_message()
        # Send initialized notification
        self.send_message({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })
        return resp


def tool_call_msg(id: int, name: str, arguments: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": id,
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments,
        }
    }


# ─── Setup ───────────────────────────────────────────────────────────────────

def setup_test_repo():
    """Create a test git repo with bingo-light initialized."""
    print("=" * 72)
    print("SETUP: Creating test repo at", TEST_REPO)
    print("=" * 72)

    if os.path.exists(TEST_REPO):
        shutil.rmtree(TEST_REPO)
    os.makedirs(TEST_REPO)

    cmds = [
        ["git", "init"],
        ["git", "config", "user.email", "fuzz@test.local"],
        ["git", "config", "user.name", "Fuzzer"],
        ["git", "config", "commit.gpgsign", "false"],
    ]
    for cmd in cmds:
        subprocess.run(cmd, cwd=TEST_REPO, capture_output=True, check=True)

    # Create initial commit
    with open(os.path.join(TEST_REPO, "README.md"), "w") as f:
        f.write("# Test repo\n")
    subprocess.run(["git", "add", "."], cwd=TEST_REPO, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=TEST_REPO, capture_output=True, check=True)

    # Create a fake upstream (local bare repo)
    upstream = TEST_REPO + "-upstream"
    if os.path.exists(upstream):
        shutil.rmtree(upstream)
    subprocess.run(["git", "clone", "--bare", TEST_REPO, upstream], capture_output=True, check=True)
    subprocess.run(["git", "remote", "add", "upstream", upstream], cwd=TEST_REPO, capture_output=True)

    # Initialize bingo-light
    result = subprocess.run(
        [BINGO_LIGHT, "init", upstream, "--yes"],
        cwd=TEST_REPO, capture_output=True, text=True
    )
    print(f"  bingo-light init: rc={result.returncode}")
    if result.returncode != 0:
        print(f"  stdout: {result.stdout[:200]}")
        print(f"  stderr: {result.stderr[:200]}")

    print("  Setup complete.\n")


# ─── Test Runner ─────────────────────────────────────────────────────────────

class Results:
    def __init__(self):
        self.tests = []

    def record(self, name, verdict, detail=""):
        self.tests.append((name, verdict, detail))
        symbol = {"OK": "\033[32mOK\033[0m", "BUG": "\033[31mBUG\033[0m", "CONCERN": "\033[33mCONCERN\033[0m"}
        print(f"  [{symbol.get(verdict, verdict):>16s}] {name}")
        if detail:
            # Truncate long details
            d = str(detail)
            if len(d) > 200:
                d = d[:200] + "..."
            print(f"           {d}")

    def summary(self):
        print("\n" + "=" * 72)
        print("SUMMARY")
        print("=" * 72)
        ok = sum(1 for _, v, _ in self.tests if v == "OK")
        bug = sum(1 for _, v, _ in self.tests if v == "BUG")
        concern = sum(1 for _, v, _ in self.tests if v == "CONCERN")
        total = len(self.tests)
        print(f"  Total: {total}  |  OK: {ok}  |  BUG: {bug}  |  CONCERN: {concern}")
        # Also emit a run-all.sh-compatible line so the aggregator picks it up.
        print(f"  {ok} passed  {bug} failed  {concern} skipped")
        print()
        if bug > 0:
            print("BUGS:")
            for name, v, detail in self.tests:
                if v == "BUG":
                    print(f"  - {name}: {detail}")
        if concern > 0:
            print("CONCERNS:")
            for name, v, detail in self.tests:
                if v == "CONCERN":
                    print(f"  - {name}: {detail}")
        print("=" * 72)


results = Results()


def run_one_test(name, msg_id, tool_name, arguments):
    """Start fresh server, initialize, send one tool call, check response."""
    client = MCPClient()
    try:
        client.start()
        init_resp = client.initialize()
        if init_resp == "TIMEOUT" or isinstance(init_resp, str) and init_resp.startswith("ERROR"):
            results.record(name, "BUG", f"Init failed: {init_resp}")
            return None

        client.send_message(tool_call_msg(msg_id, tool_name, arguments))
        resp = client.recv_message()

        if resp == "TIMEOUT":
            results.record(name, "BUG", "Server hung (timeout)")
            return None
        elif isinstance(resp, str) and resp.startswith("ERROR"):
            results.record(name, "BUG", f"Read error: {resp}")
            return None
        elif resp is None:
            results.record(name, "BUG", "Server returned None / crashed")
            return None

        # Check response structure
        if "error" in resp:
            results.record(name, "OK", f"Returned JSON-RPC error: {resp['error'].get('message', '')[:100]}")
            return resp
        elif "result" in resp:
            res = resp["result"]
            is_error = res.get("isError", False)
            text = ""
            if "content" in res and res["content"]:
                text = res["content"][0].get("text", "")[:100]
            if is_error:
                results.record(name, "OK", f"Handled gracefully (isError=true): {text}")
            else:
                results.record(name, "OK", f"Returned result: {text}")
            return resp
        else:
            results.record(name, "CONCERN", f"Unexpected response shape: {json.dumps(resp)[:150]}")
            return resp

    except BrokenPipeError:
        results.record(name, "BUG", "Server crashed (broken pipe)")
        return None
    except Exception as e:
        results.record(name, "BUG", f"Exception: {e}")
        return None
    finally:
        client.stop()


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_type_injections():
    print("\n--- TYPE INJECTION ATTACKS ---")

    run_one_test("cwd=integer(123)", 1, "bingo_status", {"cwd": 123})
    run_one_test("cwd=null", 2, "bingo_status", {"cwd": None})
    run_one_test("cwd=array", 3, "bingo_status", {"cwd": ["array"]})
    run_one_test("patch_new name=integer(123)", 4, "bingo_patch_new", {"cwd": TEST_REPO, "name": 123})
    run_one_test("patch_new name=nested_object", 5, "bingo_patch_new", {"cwd": TEST_REPO, "name": {"nested": "object"}})
    run_one_test("config action=integer(123)", 6, "bingo_config", {"cwd": TEST_REPO, "action": 123})


def test_missing_fields():
    print("\n--- MISSING REQUIRED FIELDS ---")

    run_one_test("patch_new without name", 10, "bingo_patch_new", {"cwd": TEST_REPO})
    run_one_test("patch_show without target", 11, "bingo_patch_show", {"cwd": TEST_REPO})
    run_one_test("conflict_resolve without content", 12, "bingo_conflict_resolve", {"cwd": TEST_REPO, "file": "test.txt"})
    run_one_test("sync without cwd (should default '.')", 13, "bingo_sync", {})


def test_oversized_payloads():
    print("\n--- OVERSIZED PAYLOADS ---")

    run_one_test("cwd=A*10000", 20, "bingo_status", {"cwd": "A" * 10000})

    # Oversized tool name
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        big_name = "A" * 10000
        client.send_message({
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {"name": big_name, "arguments": {"cwd": TEST_REPO}}
        })
        resp = client.recv_message()
        if resp == "TIMEOUT":
            results.record("tool_name=A*10000", "BUG", "Timeout")
        elif isinstance(resp, str) and resp.startswith("ERROR"):
            results.record("tool_name=A*10000", "BUG", f"Error: {resp}")
        elif resp and "result" in resp:
            text = resp["result"].get("content", [{}])[0].get("text", "")[:100]
            results.record("tool_name=A*10000", "OK", f"Handled: {text}")
        elif resp and "error" in resp:
            results.record("tool_name=A*10000", "OK", f"JSON-RPC error: {resp['error'].get('message','')[:100]}")
        else:
            results.record("tool_name=A*10000", "CONCERN", f"Unexpected: {str(resp)[:150]}")
    except Exception as e:
        results.record("tool_name=A*10000", "BUG", f"Exception: {e}")
    finally:
        client.stop()


def test_boundary_values():
    print("\n--- BOUNDARY VALUES ---")

    run_one_test("squash index1=0, index2=0", 30, "bingo_patch_squash", {"cwd": TEST_REPO, "index1": 0, "index2": 0})
    run_one_test("squash index1=-1, index2=1", 31, "bingo_patch_squash", {"cwd": TEST_REPO, "index1": -1, "index2": 1})
    run_one_test("squash index1=999999, index2=999999", 32, "bingo_patch_squash", {"cwd": TEST_REPO, "index1": 999999, "index2": 999999})
    run_one_test("reorder order='0'", 33, "bingo_patch_reorder", {"cwd": TEST_REPO, "order": "0"})
    run_one_test("reorder order=''", 34, "bingo_patch_reorder", {"cwd": TEST_REPO, "order": ""})


def test_protocol_rapid_fire():
    """Send 100 rapid messages and count how many get responses."""
    print("\n--- PROTOCOL: RAPID FIRE (100 messages) ---")

    client = MCPClient()
    try:
        client.start()
        client.initialize()

        COUNT = 100
        # Send all 100 as fast as possible
        for i in range(1, COUNT + 1):
            client.send_message({
                "jsonrpc": "2.0",
                "id": 1000 + i,
                "method": "ping",
            })

        # Collect responses
        received = 0
        ids_seen = set()
        start = time.time()
        while received < COUNT and (time.time() - start) < 15:
            resp = client.recv_message(timeout=3)
            if resp == "TIMEOUT":
                break
            if isinstance(resp, str) and resp.startswith("ERROR"):
                break
            if resp and isinstance(resp, dict):
                received += 1
                ids_seen.add(resp.get("id"))

        if received == COUNT:
            results.record(f"rapid_fire: {COUNT} pings", "OK", f"All {COUNT} responses received")
        elif received == 0:
            results.record(f"rapid_fire: {COUNT} pings", "BUG", "No responses received")
        else:
            missing = COUNT - received
            results.record(f"rapid_fire: {COUNT} pings", "BUG", f"Only {received}/{COUNT} responses ({missing} dropped)")

    except Exception as e:
        results.record(f"rapid_fire: {COUNT} pings", "BUG", f"Exception: {e}")
    finally:
        client.stop()


def test_protocol_content_length_mismatch():
    """Send Content-Length: 999999 but only 10 bytes. Should it hang?"""
    print("\n--- PROTOCOL: Content-Length mismatch ---")

    client = MCPClient()
    try:
        client.start()
        client.initialize()

        # Send a header claiming 999999 bytes but only write 10
        header = b"Content-Length: 999999\r\n\r\n"
        partial = b'{"jsonrpc"'  # 10 bytes, incomplete
        client.send_raw(header + partial)

        # Now try to read -- this SHOULD timeout because the server is blocked
        # waiting for 999999 bytes. We test whether the server hangs forever.
        resp = client.recv_message(timeout=5)

        if resp == "TIMEOUT":
            results.record("content-length mismatch (999999 vs 10 bytes)", "CONCERN",
                           "Server blocked on stdin.read(999999) -- expected but DoS risk if no timeout")
        elif isinstance(resp, str) and resp.startswith("ERROR"):
            results.record("content-length mismatch (999999 vs 10 bytes)", "OK",
                           f"Server handled it: {resp}")
        else:
            results.record("content-length mismatch (999999 vs 10 bytes)", "OK",
                           f"Unexpected graceful response: {str(resp)[:100]}")
    except Exception as e:
        results.record("content-length mismatch (999999 vs 10 bytes)", "BUG", f"Exception: {e}")
    finally:
        client.stop()


def test_protocol_back_to_back():
    """Send two messages with no gap -- does it parse both?"""
    print("\n--- PROTOCOL: Back-to-back messages ---")

    client = MCPClient()
    try:
        client.start()
        client.initialize()

        # Build two messages and send them as one write
        msg1 = json.dumps({"jsonrpc": "2.0", "id": 2001, "method": "ping"}).encode("utf-8")
        msg2 = json.dumps({"jsonrpc": "2.0", "id": 2002, "method": "ping"}).encode("utf-8")

        frame1 = f"Content-Length: {len(msg1)}\r\n\r\n".encode("utf-8") + msg1
        frame2 = f"Content-Length: {len(msg2)}\r\n\r\n".encode("utf-8") + msg2

        # Single write, both messages concatenated
        client.send_raw(frame1 + frame2)

        resp1 = client.recv_message(timeout=3)
        resp2 = client.recv_message(timeout=3)

        got1 = isinstance(resp1, dict) and resp1.get("id") in (2001, 2002)
        got2 = isinstance(resp2, dict) and resp2.get("id") in (2001, 2002)

        if got1 and got2:
            results.record("back-to-back messages", "OK", "Both responses received correctly")
        elif got1 and not got2:
            results.record("back-to-back messages", "BUG",
                           f"Only first response received (resp2={resp2})")
        else:
            results.record("back-to-back messages", "BUG",
                           f"resp1={resp1}, resp2={resp2}")

    except Exception as e:
        results.record("back-to-back messages", "BUG", f"Exception: {e}")
    finally:
        client.stop()


# Some extra edge cases for completeness

def test_extra_edge_cases():
    print("\n--- EXTRA EDGE CASES ---")

    # Unknown method with id -> should get error response
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        client.send_message({"jsonrpc": "2.0", "id": 3001, "method": "bogus/method", "params": {}})
        resp = client.recv_message()
        if isinstance(resp, dict) and "error" in resp:
            results.record("unknown method with id", "OK", f"Returned error: {resp['error'].get('message','')[:80]}")
        elif resp == "TIMEOUT":
            results.record("unknown method with id", "BUG", "No response for unknown method")
        else:
            results.record("unknown method with id", "CONCERN", f"Unexpected: {str(resp)[:100]}")
    finally:
        client.stop()

    # Unknown method without id (notification) -> should be silently ignored
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        client.send_message({"jsonrpc": "2.0", "method": "bogus/notification", "params": {}})
        # Send a ping right after to see if server is still alive
        client.send_message({"jsonrpc": "2.0", "id": 3002, "method": "ping"})
        resp = client.recv_message()
        if isinstance(resp, dict) and resp.get("id") == 3002:
            results.record("unknown notification (no id)", "OK", "Silently ignored, server alive")
        elif resp == "TIMEOUT":
            results.record("unknown notification (no id)", "BUG", "Server hung after unknown notification")
        else:
            results.record("unknown notification (no id)", "CONCERN", f"Unexpected: {str(resp)[:100]}")
    finally:
        client.stop()

    # Empty params
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        client.send_message({"jsonrpc": "2.0", "id": 3003, "method": "tools/call", "params": {}})
        resp = client.recv_message()
        if isinstance(resp, dict) and "result" in resp:
            text = resp["result"].get("content", [{}])[0].get("text", "")[:80]
            results.record("tools/call with empty params", "OK", f"Handled: {text}")
        elif isinstance(resp, dict) and "error" in resp:
            results.record("tools/call with empty params", "OK", f"Error response: {resp['error'].get('message','')[:80]}")
        elif resp == "TIMEOUT":
            results.record("tools/call with empty params", "BUG", "Timeout")
        else:
            results.record("tools/call with empty params", "CONCERN", f"Unexpected: {str(resp)[:100]}")
    finally:
        client.stop()

    # Malformed JSON body with valid Content-Length
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        garbage = b"{{{{not json at all!!!}}"
        header = f"Content-Length: {len(garbage)}\r\n\r\n".encode("utf-8")
        client.send_raw(header + garbage)
        # Server should handle this -- either error response or close connection
        # Send another ping to see if server survived
        time.sleep(0.2)
        alive = client.proc.poll() is None
        if alive:
            client.send_message({"jsonrpc": "2.0", "id": 3004, "method": "ping"})
            resp = client.recv_message(timeout=3)
            if isinstance(resp, dict) and resp.get("id") == 3004:
                results.record("malformed JSON body", "CONCERN",
                               "Server silently discarded bad JSON and continued (no error sent)")
            elif resp == "TIMEOUT":
                results.record("malformed JSON body", "BUG", "Server hung after malformed JSON")
            else:
                results.record("malformed JSON body", "CONCERN", f"Unexpected: {str(resp)[:100]}")
        else:
            results.record("malformed JSON body", "BUG", f"Server exited with code {client.proc.returncode}")
    except Exception as e:
        results.record("malformed JSON body", "BUG", f"Exception: {e}")
    finally:
        client.stop()

    # Path traversal in cwd
    run_one_test("cwd=path_traversal ../../etc", 3005, "bingo_status", {"cwd": "/etc"})
    run_one_test("cwd=path_traversal /dev/null", 3006, "bingo_status", {"cwd": "/dev/null"})

    # Null bytes in strings
    run_one_test("cwd with null bytes", 3007, "bingo_status", {"cwd": "/tmp/mcp-fuzz\x00/evil"})
    run_one_test("name with shell metacharacters", 3008, "bingo_patch_new",
                 {"cwd": TEST_REPO, "name": "; rm -rf / #"})
    run_one_test("name with backticks", 3009, "bingo_patch_new",
                 {"cwd": TEST_REPO, "name": "`id`"})
    run_one_test("name with $() injection", 3010, "bingo_patch_new",
                 {"cwd": TEST_REPO, "name": "$(whoami)"})


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("MCP Server Fuzzer for bingo-light")
    print("Server:", MCP_SERVER)
    print("CLI:", BINGO_LIGHT)
    print()

    setup_test_repo()

    test_type_injections()
    test_missing_fields()
    test_oversized_payloads()
    test_boundary_values()
    test_protocol_rapid_fire()
    test_protocol_content_length_mismatch()
    test_protocol_back_to_back()
    test_extra_edge_cases()

    results.summary()

    # Exit code: 1 if any BUGs
    bugs = sum(1 for _, v, _ in results.tests if v == "BUG")
    sys.exit(1 if bugs > 0 else 0)


if __name__ == "__main__":
    main()
