import type { ExecutionStatus } from '@/utils/state-machine'

export function mapOptimisticExecutionStatus(status: string | null | undefined): ExecutionStatus | null {
  if (status === 'Stopping...') return 'cancelled'
  if (status === 'Starting...') return 'running'
  return null
}

export function describeExecutionStatus(status: ExecutionStatus, optimisticStatus?: string | null): string {
  if (optimisticStatus === 'Starting...') {
    return 'Starting run snapshot and execution monitor.'
  }
  if (optimisticStatus === 'Stopping...') {
    return 'Stopping execution; completed logs and artifacts are being preserved.'
  }

  switch (status) {
    case 'running':
      return 'Worker is executing saved run resources.'
    case 'failed':
      return 'Run failed; inspect diagnostics and logs before retry or rerun.'
    case 'completed':
      return 'Run completed; results and artifacts are available if produced.'
    case 'cancelled':
      return 'Run was stopped or cancelled; completed artifacts are preserved.'
    case 'pending':
    default:
      return 'Ready to validate, save, and execute.'
  }
}
