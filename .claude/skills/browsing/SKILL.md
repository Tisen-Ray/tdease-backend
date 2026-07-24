---
name: browsing
description: Direct Chrome browser control via DevTools Protocol. Use when controlling authenticated sessions, managing multiple tabs, or when Playwright MCP is unavailable. Uses the use_browser MCP tool.
allowed-tools: mcp__chrome__use_browser
---

# Browsing with Chrome Direct

Control Chrome via DevTools Protocol using the `use_browser` MCP tool.
Single unified interface with auto-starting Chrome.

**Announce:** "Using browsing skill to control Chrome."

## When to Use

- Controlling authenticated sessions
- Managing multiple tabs in running browser
- Playwright unavailable or excessive

Use `playwright-cli` when you need fresh browser instances, screenshots/PDFs, or higher-level abstractions.

## Auto-Capture

Every DOM action (navigate, click, type, select, eval, keyboard_press, hover,
drag_drop, double_click, right_click, file_upload) automatically saves:
- `{prefix}.png` — viewport screenshot
- `{prefix}.md` — page content as structured markdown
- `{prefix}.html` — full rendered DOM
- `{prefix}-console.txt` — browser console messages

Prefer reading these files to using 'extract' or 'screenshot' whenever possible.

## Core Actions

| Action | Selector | Payload | Notes |
|--------|----------|---------|-------|
| `navigate` | — | URL string | Auto-captures after load |
| `click` | CSS/XPath | — | Auto-captures after click |
| `type` | CSS/XPath | text string | Types into input/textarea |
| `eval` | — | JS string | Execute JavaScript in page |
| `select` | CSS/XPath | option value | Select dropdown option |
| `extract` | CSS/XPath | format: markdown/html/text | Extract element content |
| `screenshot` | CSS/XPath | fullpage: true/false | Capture viewport or full page |
| `new_tab` | — | URL | Open new tab |
| `switch_tab` | — | tab index or URL substring | Switch active tab |
| `list_tabs` | — | — | List all tabs |
| `close_tab` | — | tab index | Close a tab |
| `back` / `forward` | — | — | Browser navigation |
| `hover` / `scroll` | CSS/XPath | direction or {deltaX,deltaY} | Hover or scroll |
| `keyboard_press` | — | key string or {key, modifiers} | Keyboard input |
| `await_element` | CSS/XPath | timeout ms | Wait for element to appear |
| `await_text` | CSS/XPath | text or {text, timeout} | Wait for text to appear |

## Selector Types

- **CSS:** `button.submit`, `#login-form`, `input[name="email"]`
- **XPath:** `//button[contains(text(),'Submit')]`
- **Special:** `dialog::accept`, `dialog::dismiss` for dialogs

## Advanced

- `set_viewport`: `{width, height, mobile?}`
- `clear_cookies`: Clears all browser cookies
- `file_upload`: `{files: ["path/to/file"]}`
- `drag_drop`: `{x, y}` or selector string for target
- `mouse_move`: `{x, y, steps?, fromX?, fromY?}`
- `get_console_messages`: `{since: epochMs}`

Use `action='help'` for full per-action documentation.
