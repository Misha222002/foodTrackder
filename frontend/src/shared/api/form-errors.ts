import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'

export function applyFormErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  allowed: readonly Path<T>[],
) {
  if (!error || typeof error !== 'object' || !('data' in error)) return
  const fields = (error.data as { details?: { fields?: { path: string; message: string }[] } })
    ?.details?.fields
  for (const field of fields ?? []) {
    if (allowed.includes(field.path as Path<T>))
      setError(
        field.path as Path<T>,
        { type: 'server', message: field.message },
        { shouldFocus: true },
      )
  }
}
