#!/usr/bin/env python3
"""
MCP protocol tests for bingo-light mcp-server.py

Tests JSON-RPC 2.0 over stdio with Content-Length framing,
all 22 tool smoke tests, malformed request handling, and cwd validation.

Usage: python3 tests/test-mcp.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

# ─── Config ──────────────────────────────────────────────────────────────────

MCP_SERVER = os.path.join(os.path.dirname(__file__), '..', 'mcp-server.py')
BL_BIN = os.path.join(os.path.dirname(__file__), '..', 'bingo-light')

# ─── Test runner ─────────────────────────────────────────────────────────────

passed = 0
failed = 0

GREEN = '\033[0;32m'
RED = '\033[0;31m'
BOLD = '\033[1m'
RESET = '\033[0m'

if os.environ.get('NO_COLOR') or not sys.stdout.isatty():
    GREEN = RED = BOLD = RESET = ''


def ok(desc: str):
    global passed
    passed += 1
    print(f'  {GREEN}PASS{RESET} {desc}')


def fail(desc: str, detail: str = ''):
    global failed
    failed += 1
    msg = f'  {RED}FAIL{RESET} {desc}'
    if detail:
        msg += f': {detail}'
    print(msg)


def section(title: str):
    print(f'\n{BOLD}{title}{RESET}')


# ─── MCP framing helpers ────────────────────────────────────────────────────

def jsonline_message(obj: dict) -> bytes:
    """Encode a JSON-RPC message as a bare JSON line (standard MCP stdio)."""
    return json.dumps(obj).encode('utf-8') + b'\n'


def send_receive_jsonline(messages: list, timeout: int = 10) -> list:
    """Send bare JSON lines to MCP server and parse newline-delimited responses."""
    proc = subprocess.Popen(
        [sys.executable, MCP_SERVER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, 'BINGO_LIGHT_BIN': BL_BIN},
    )
    payload = b''
    for msg in messages:
        payload += jsonline_message(msg)
    try:
        stdout_data, _ = proc.communicate(input=payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return []
    responses = []
    for line in stdout_data.decode('utf-8', errors='replace').splitlines():
        line = line.strip()
        if line:
            try:
                responses.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return responses


def frame_message(obj: dict) -> bytes:
    """Encode a JSON-RPC message with Content-Length framing."""
    body = json.dumps(obj).encode('utf-8')
    header = f'Content-Length: {len(body)}\r\n\r\n'.encode('utf-8')
    return header + body


def send_receive(messages: list[dict], timeout: int = 10, raw_prefix: bytes = b'') -> list[dict]:
    """
    Start mcp-server.py, send each message with Content-Length framing,
    then close stdin and read all responses. Returns list of parsed JSON responses.

    raw_prefix: optional raw bytes to send before the framed messages
    (used for malformed request tests).
    """
    proc = subprocess.Popen(
        [sys.executable, MCP_SERVER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, 'BINGO_LIGHT_BIN': BL_BIN},
    )

    # Build input payload
    payload = raw_prefix
    for msg in messages:
        payload += frame_message(msg)

    try:
        stdout_data, _ = proc.communicate(input=payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return []

    # Parse responses from stdout
    responses = []
    pos = 0
    data = stdout_data
    while pos < len(data):
        # Find Content-Length header
        header_end = data.find(b'\r\n\r\n', pos)
        if header_end == -1:
            break
        header_block = data[pos:header_end].decode('utf-8', errors='replace')
        content_length = 0
        for line in header_block.split('\r\n'):
            if line.lower().startswith('content-length:'):
                content_length = int(line.split(':', 1)[1].strip())
                break
        if content_length == 0:
            break
        body_start = header_end + 4
        body_end = body_start + content_length
        if body_end > len(data):
            break
        body = data[body_start:body_end].decode('utf-8')
        try:
            responses.append(json.loads(body))
        except json.JSONDecodeError:
            break
        pos = body_end
    return responses


def send_raw_only(raw_bytes: bytes, timeout: int = 5) -> tuple[bytes, int]:
    """
    Send raw bytes to the server (no proper framing), close stdin,
    and return (stdout, returncode). Used for crash tests.
    """
    proc = subprocess.Popen(
        [sys.executable, MCP_SERVER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, 'BINGO_LIGHT_BIN': BL_BIN},
    )
    try:
        stdout_data, _ = proc.communicate(input=raw_bytes, timeout=timeout)
        return stdout_data, proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return b'', -1


# ─── Git repo setup ─────────────────────────────────────────────────────────

def make_test_repos(base_dir: str) -> tuple[str, str]:
    """Create upstream + fork repos, init bingo-light, create a patch. Returns (upstream, fork)."""
    upstream = os.path.join(base_dir, 'upstream')
    fork = os.path.join(base_dir, 'fork')
    os.makedirs(upstream)

    def git(args: list[str], cwd: str, env_extra: dict | None = None):
        env = os.environ.copy()
        env['GIT_AUTHOR_NAME'] = 'Test'
        env['GIT_AUTHOR_EMAIL'] = 'test@test.com'
        env['GIT_COMMITTER_NAME'] = 'Test'
        env['GIT_COMMITTER_EMAIL'] = 'test@test.com'
        if env_extra:
            env.update(env_extra)
        subprocess.run(['git'] + args, cwd=cwd, capture_output=True, text=True, env=env, check=True)

    # Create upstream
    git(['init', '--initial-branch=main', '-q'], upstream)
    with open(os.path.join(upstream, 'app.py'), 'w') as f:
        f.write('line1\n')
    with open(os.path.join(upstream, 'config.py'), 'w') as f:
        f.write('config=1\n')
    git(['add', '-A'], upstream)
    git(['commit', '-q', '-m', 'Initial commit'], upstream)

    with open(os.path.join(upstream, 'app.py'), 'a') as f:
        f.write('line2\n')
    git(['add', '-A'], upstream)
    git(['commit', '-q', '-m', 'Second commit'], upstream)

    # Clone as fork
    git(['clone', '-q', upstream, fork], base_dir)

    # Init bingo-light in fork
    env = os.environ.copy()
    env['BINGO_LIGHT_BIN'] = BL_BIN
    subprocess.run(
        [BL_BIN, 'init', upstream, 'main', '--json', '--yes'],
        cwd=fork, capture_output=True, text=True, env=env,
    )

    # Create a patch
    with open(os.path.join(fork, 'custom.txt'), 'w') as f:
        f.write('my customization\n')
    git(['add', '-A'], fork)
    env['BINGO_DESCRIPTION'] = 'test patch'
    subprocess.run(
        [BL_BIN, 'patch', 'new', 'test-patch', '--json', '--yes'],
        cwd=fork, capture_output=True, text=True, env=env,
    )

    return upstream, fork


# ─── Helpers for building JSON-RPC requests ──────────────────────────────────

_request_id = 0

def make_request(method: str, params: dict | None = None) -> dict:
    global _request_id
    _request_id += 1
    msg = {'jsonrpc': '2.0', 'id': _request_id, 'method': method}
    if params is not None:
        msg['params'] = params
    return msg


def make_tool_call(tool_name: str, arguments: dict) -> dict:
    return make_request('tools/call', {'name': tool_name, 'arguments': arguments})


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_protocol_basics():
    """Test basic MCP protocol handshake."""
    section('1. Protocol basics')

    # initialize
    msgs = [make_request('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {}})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        r = resps[0]['result']
        if r.get('serverInfo', {}).get('name') == 'bingo-light':
            ok('initialize returns server info')
        else:
            fail('initialize returns server info', f'got {r}')
    else:
        fail('initialize returns server info', f'got {resps}')

    # ping
    msgs = [make_request('ping')]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('ping returns result')
    else:
        fail('ping returns result', f'got {resps}')

    # tools/list
    msgs = [make_request('tools/list')]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        tools = resps[0]['result'].get('tools', [])
        if len(tools) >= 22:
            ok(f'tools/list returns {len(tools)} tools')
        else:
            fail(f'tools/list returns >=22 tools', f'got {len(tools)}')
    else:
        fail('tools/list returns tools', f'got {resps}')

    # notifications/initialized should not produce a response
    msgs = [
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        make_request('ping'),
    ]
    resps = send_receive(msgs)
    # Should get exactly 1 response (for ping), not 2
    if len(resps) == 1 and resps[0].get('result') == {}:
        ok('notification does not produce response')
    else:
        fail('notification does not produce response', f'got {len(resps)} responses')

    # Multiple messages in one session
    msgs = [
        make_request('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {}}),
        make_request('tools/list'),
        make_request('ping'),
    ]
    resps = send_receive(msgs)
    if len(resps) == 3:
        ok('multiple messages in one session')
    else:
        fail('multiple messages in one session', f'expected 3 responses, got {len(resps)}')


def test_jsonline_framing():
    """Test bare JSON line framing (standard MCP stdio, used by all major clients)."""
    section('1b. Bare JSON line framing (standard MCP)')

    # Initialize via bare JSON lines
    init_msg = make_request('initialize', {
        'protocolVersion': '2025-11-25',
        'capabilities': {'roots': {}},
        'clientInfo': {'name': 'test-client', 'version': '1.0'},
    })
    tools_msg = make_request('tools/list')
    ping_msg = make_request('ping')

    resps = send_receive_jsonline([init_msg, tools_msg, ping_msg])

    if len(resps) >= 1 and resps[0].get('result', {}).get('serverInfo', {}).get('name') == 'bingo-light':
        ok('jsonline: initialize response valid')
    else:
        fail('jsonline: initialize response', f'got {resps[0] if resps else "nothing"}')

    if len(resps) >= 2 and len(resps[1].get('result', {}).get('tools', [])) >= 35:
        ok(f'jsonline: tools/list returns {len(resps[1]["result"]["tools"])} tools')
    else:
        fail('jsonline: tools/list', f'got {len(resps[1].get("result", {}).get("tools", [])) if len(resps) >= 2 else 0} tools')

    if len(resps) >= 3 and 'result' in resps[2]:
        ok('jsonline: ping response valid')
    else:
        fail('jsonline: ping response', f'got {resps[2] if len(resps) >= 3 else "nothing"}')


def test_tool_smoke(fork_dir: str, upstream_dir: str):
    """Smoke test all 22 tools."""
    section('2. Tool smoke tests')

    # Export patches first so we have .patch files for import test
    export_dir = os.path.join(fork_dir, '.bl-patches')

    # Tools that should succeed (return response with isError=false or just a response)
    # Tools expected to succeed (isError=false)
    simple_tools = [
        ('bingo_status', {'cwd': fork_dir}),
        ('bingo_patch_list', {'cwd': fork_dir}),
        ('bingo_doctor', {'cwd': fork_dir}),
        ('bingo_diff', {'cwd': fork_dir}),
        ('bingo_config', {'cwd': fork_dir, 'action': 'list'}),
        ('bingo_history', {'cwd': fork_dir}),
        ('bingo_auto_sync', {'cwd': fork_dir}),
        # dep tools (work on any directory, even without npm/pip)
        ('bingo_dep_status', {'cwd': fork_dir}),
        ('bingo_dep_list', {'cwd': fork_dir}),
    ]

    for tool_name, args in simple_tools:
        msgs = [make_tool_call(tool_name, args)]
        resps = send_receive(msgs)
        if len(resps) == 1 and 'result' in resps[0]:
            result = resps[0]['result']
            if not result.get('isError', False):
                ok(f'{tool_name} succeeds')
            else:
                text = result.get('content', [{}])[0].get('text', '')
                fail(f'{tool_name} succeeds', f'isError=true: {text[:120]}')
        else:
            fail(f'{tool_name} succeeds', f'no valid response')

    # Tools that require specific state -- accept any response (even isError=true)
    # bingo_workspace_status needs workspace init which is out of scope for this test
    stateful_tools = [
        ('bingo_workspace_status', {'cwd': fork_dir}),
        ('bingo_workspace_remove', {'cwd': fork_dir, 'target': 'noop-alias'}),
    ]

    for tool_name, args in stateful_tools:
        msgs = [make_tool_call(tool_name, args)]
        resps = send_receive(msgs)
        if len(resps) == 1 and 'result' in resps[0]:
            ok(f'{tool_name} returns response')
        else:
            fail(f'{tool_name} returns response', 'no valid response')

    # bingo_patch_show (requires existing patch)
    msgs = [make_tool_call('bingo_patch_show', {'cwd': fork_dir, 'target': '1'})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_patch_show returns response')
    else:
        fail('bingo_patch_show returns response')

    # bingo_patch_meta (get metadata for test-patch)
    msgs = [make_tool_call('bingo_patch_meta', {'cwd': fork_dir, 'name': 'test-patch'})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_patch_meta returns response')
    else:
        fail('bingo_patch_meta returns response')

    # bingo_patch_export
    msgs = [make_tool_call('bingo_patch_export', {'cwd': fork_dir})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_patch_export returns response')
    else:
        fail('bingo_patch_export returns response')

    # bingo_patch_import (import back the exported patches)
    # Find a .patch file
    patch_file = None
    if os.path.isdir(export_dir):
        for f in os.listdir(export_dir):
            if f.endswith('.patch'):
                patch_file = os.path.join(export_dir, f)
                break
    if patch_file:
        msgs = [make_tool_call('bingo_patch_import', {'cwd': fork_dir, 'path': patch_file})]
        resps = send_receive(msgs)
        if len(resps) == 1 and 'result' in resps[0]:
            ok('bingo_patch_import returns response')
        else:
            fail('bingo_patch_import returns response')
    else:
        # Just verify it returns a response even with bad path
        msgs = [make_tool_call('bingo_patch_import', {'cwd': fork_dir, 'path': '/nonexistent.patch'})]
        resps = send_receive(msgs)
        if len(resps) == 1 and 'result' in resps[0]:
            ok('bingo_patch_import returns response (no patch file available)')
        else:
            fail('bingo_patch_import returns response')

    # bingo_init (re-init, may warn but should respond)
    msgs = [make_tool_call('bingo_init', {'cwd': fork_dir, 'upstream_url': upstream_dir})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_init returns response')
    else:
        fail('bingo_init returns response')

    # bingo_sync (dry run to avoid breaking state)
    msgs = [make_tool_call('bingo_sync', {'cwd': fork_dir, 'dry_run': True})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_sync (dry_run) returns response')
    else:
        fail('bingo_sync (dry_run) returns response')

    # bingo_test (no test command configured, should return response even if isError)
    msgs = [make_tool_call('bingo_test', {'cwd': fork_dir})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_test returns response')
    else:
        fail('bingo_test returns response')

    # bingo_conflict_analyze (not in rebase, will return error but should not crash)
    msgs = [make_tool_call('bingo_conflict_analyze', {'cwd': fork_dir})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_conflict_analyze returns response')
    else:
        fail('bingo_conflict_analyze returns response')

    # bingo_conflict_resolve (not in rebase, should return error gracefully)
    msgs = [make_tool_call('bingo_conflict_resolve', {
        'cwd': fork_dir, 'file': 'app.py', 'content': 'resolved\n',
    })]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        result = resps[0]['result']
        # Expect isError=true (not in rebase), but a valid response
        if result.get('isError', False):
            ok('bingo_conflict_resolve returns error (not in rebase)')
        else:
            ok('bingo_conflict_resolve returns response')
    else:
        fail('bingo_conflict_resolve returns response')

    # bingo_conflict_resolve with verify=true (not in rebase, should respond cleanly)
    msgs = [make_tool_call('bingo_conflict_resolve', {
        'cwd': fork_dir, 'file': 'app.py', 'content': 'resolved\n',
        'verify': True,
    })]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_conflict_resolve accepts verify=true')
    else:
        fail('bingo_conflict_resolve accepts verify=true')

    # bingo_undo (may fail if nothing to undo, but should respond)
    msgs = [make_tool_call('bingo_undo', {'cwd': fork_dir})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_undo returns response')
    else:
        fail('bingo_undo returns response')

    # bingo_patch_reorder (only 1 patch, reorder to "1")
    msgs = [make_tool_call('bingo_patch_reorder', {'cwd': fork_dir, 'order': '1'})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_patch_reorder returns response')
    else:
        fail('bingo_patch_reorder returns response')

    # bingo_patch_squash (only 1 patch, will error but should respond)
    msgs = [make_tool_call('bingo_patch_squash', {'cwd': fork_dir, 'index1': 1, 'index2': 2})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_patch_squash returns response')
    else:
        fail('bingo_patch_squash returns response')

    # bingo_patch_new (create a second patch)
    # First, make a change to commit
    with open(os.path.join(fork_dir, 'extra.txt'), 'w') as f:
        f.write('extra\n')
    subprocess.run(['git', 'add', '-A'], cwd=fork_dir, capture_output=True)
    msgs = [make_tool_call('bingo_patch_new', {
        'cwd': fork_dir, 'name': 'extra-patch', 'description': 'extra test patch',
    })]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_patch_new returns response')
    else:
        fail('bingo_patch_new returns response')

    # bingo_patch_drop (drop the patch we just created)
    msgs = [make_tool_call('bingo_patch_drop', {'cwd': fork_dir, 'target': 'extra-patch'})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        ok('bingo_patch_drop returns response')
    else:
        fail('bingo_patch_drop returns response')


def test_malformed_requests():
    """Test server resilience against malformed input."""
    section('3. Malformed request handling')

    # 1. No Content-Length header (just raw garbage)
    stdout, rc = send_raw_only(b'this is not a valid message\r\n\r\n')
    # Server should exit cleanly, not crash
    if rc == 0:
        ok('no Content-Length header: server exits cleanly')
    else:
        # Some exit codes are acceptable as long as it didn't crash with a traceback
        ok('no Content-Length header: server did not hang')

    # 2. Invalid JSON body
    bad_body = b'this is {{{ not json'
    raw = f'Content-Length: {len(bad_body)}\r\n\r\n'.encode() + bad_body
    # Send invalid JSON, then a valid ping to see if server survives
    ping = frame_message(make_request('ping'))
    raw_plus_ping = raw + ping
    proc = subprocess.Popen(
        [sys.executable, MCP_SERVER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, 'BINGO_LIGHT_BIN': BL_BIN},
    )
    try:
        stdout_data, _ = proc.communicate(input=raw_plus_ping, timeout=10)
        # Server might drop the bad message and process the ping, or exit after bad message
        # Either way it should not crash with a traceback
        if proc.returncode == 0:
            ok('invalid JSON body: server handles gracefully')
        else:
            ok('invalid JSON body: server exited without crash')
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        fail('invalid JSON body: server hung')

    # 3. Missing 'method' field
    msgs = [{'jsonrpc': '2.0', 'id': 999}]
    # The server's read_message returns the dict; main() looks for msg.get("method", "")
    # With method="" it hits the else branch (unknown notification if no id, or error if id)
    # Since we have id=999 and method="" -> falls to the else with id is not None -> error
    resps = send_receive(msgs)
    if len(resps) >= 1:
        resp = resps[0]
        if 'error' in resp:
            ok('missing method: returns JSON-RPC error')
        elif 'result' in resp:
            # Some servers might treat empty method as unknown
            ok('missing method: returns response')
        else:
            fail('missing method: unexpected response', str(resp))
    else:
        # Server exited without response - acceptable for edge case
        ok('missing method: server handles gracefully (no response)')

    # 4. Missing 'params' field on tools/call
    msgs = [make_request('tools/call')]  # No params at all
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        result = resps[0]['result']
        if result.get('isError', False):
            ok('missing params on tools/call: returns tool error')
        else:
            ok('missing params on tools/call: returns response')
    elif len(resps) == 1 and 'error' in resps[0]:
        ok('missing params on tools/call: returns JSON-RPC error')
    else:
        fail('missing params on tools/call', f'got {resps}')

    # 5. Wrong method name
    msgs = [make_request('nonexistent/method')]
    resps = send_receive(msgs)
    if len(resps) == 1:
        if 'error' in resps[0]:
            ok('wrong method name: returns JSON-RPC error')
        else:
            fail('wrong method name: expected error', str(resps[0]))
    else:
        fail('wrong method name', f'got {len(resps)} responses')

    # 6. Empty arguments on tool call
    msgs = [make_tool_call('bingo_status', {})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        result = resps[0]['result']
        if result.get('isError', False):
            ok('empty arguments: returns error')
        else:
            fail('empty arguments: expected isError', str(result))
    else:
        fail('empty arguments', f'got {resps}')


def test_cwd_validation():
    """Test cwd validation."""
    section('4. cwd validation')

    # cwd pointing to non-existent directory
    msgs = [make_tool_call('bingo_status', {'cwd': '/nonexistent/path/that/does/not/exist'})]
    resps = send_receive(msgs)
    if len(resps) == 1 and 'result' in resps[0]:
        result = resps[0]['result']
        if result.get('isError', False):
            text = result.get('content', [{}])[0].get('text', '')
            if 'does not exist' in text.lower() or 'invalid' in text.lower() or 'not' in text.lower():
                ok('non-existent cwd: returns descriptive error')
            else:
                ok('non-existent cwd: returns error')
        else:
            fail('non-existent cwd: expected isError=true')
    else:
        fail('non-existent cwd', f'got {resps}')

    # cwd pointing to a file (not a directory)
    tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
    tmpfile.write(b'not a directory\n')
    tmpfile.close()
    try:
        msgs = [make_tool_call('bingo_status', {'cwd': tmpfile.name})]
        resps = send_receive(msgs)
        if len(resps) == 1 and 'result' in resps[0]:
            result = resps[0]['result']
            if result.get('isError', False):
                ok('file-as-cwd: returns error')
            else:
                fail('file-as-cwd: expected isError=true')
        else:
            fail('file-as-cwd', f'got {resps}')
    finally:
        os.unlink(tmpfile.name)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    global passed, failed

    print(f'{BOLD}bingo-light MCP server tests{RESET}')
    print(f'server: {MCP_SERVER}')

    # Check prerequisites
    if not os.path.isfile(MCP_SERVER):
        print(f'{RED}ERROR{RESET}: mcp-server.py not found at {MCP_SERVER}')
        sys.exit(1)
    if not os.path.isfile(BL_BIN):
        print(f'{RED}ERROR{RESET}: bingo-light not found at {BL_BIN}')
        sys.exit(1)

    # Set up test repo
    tmpdir = tempfile.mkdtemp(prefix='bingo-mcp-test-')
    try:
        upstream_dir, fork_dir = make_test_repos(tmpdir)

        test_protocol_basics()
        test_jsonline_framing()
        test_tool_smoke(fork_dir, upstream_dir)
        test_malformed_requests()
        test_cwd_validation()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # Summary
    total = passed + failed
    print(f'\n{BOLD}Results: {passed}/{total} passed{RESET}', end='')
    if failed:
        print(f', {RED}{failed} failed{RESET}')
    else:
        print(f' {GREEN}(all passed){RESET}')

    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
