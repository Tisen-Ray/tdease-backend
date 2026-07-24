export function normalizeWorkspaceRelativePath(path: string | null | undefined): string {
  return String(path ?? '')
    .trim()
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
    .replace(/\/+/g, '/')
}

export function splitWorkspacePath(path: string | null | undefined): string[] {
  return normalizeWorkspaceRelativePath(path)
    .split('/')
    .map((segment) => segment.trim())
    .filter(Boolean)
}
