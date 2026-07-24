import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkspaceStore } from './workspace'

type MockClient = {
  get: ReturnType<typeof vi.fn>
}

function createWorkspaceClient(): MockClient {
  return {
    get: vi.fn(async (_url: string, params?: Record<string, unknown>) => {
      if (!params?.path) {
        return {
          data: {
            user_id: 'user-1',
            workspace_id: 'workspace-1',
            tree: [
              { name: 'data', type: 'directory', path: 'data' },
              { name: 'runs', type: 'directory', path: 'runs' },
              { name: 'notes.txt', type: 'file', path: 'notes.txt' },
            ],
          },
        }
      }

      return {
        data: {
          user_id: 'user-1',
          workspace_id: 'workspace-1',
          tree: [],
        },
      }
    }),
  }
}

describe('workspace store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
  })

  it('preloads only root-present canonical directories from the root listing', async () => {
    const client = createWorkspaceClient()
    const store = useWorkspaceStore()
    store.setApiClient(client as any)
    store.setWorkspace('user-1', 'workspace-1')

    await store.loadFileTree()
    await vi.waitFor(() => {
      expect(client.get).toHaveBeenCalledWith(
        '/api/users/user-1/workspaces/workspace-1/files',
        { path: 'data' }
      )
      expect(client.get).toHaveBeenCalledWith(
        '/api/users/user-1/workspaces/workspace-1/files',
        { path: 'runs' }
      )
    })

    const requestedPaths = client.get.mock.calls
      .map(([, params]) => params?.path)
      .filter(Boolean)

    expect(requestedPaths).toEqual(['data', 'runs'])
    expect(requestedPaths).not.toContain('reference')
    expect(requestedPaths).not.toContain('logs')
    expect(requestedPaths).not.toContain('results')
  })
})
