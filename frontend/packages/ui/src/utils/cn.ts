import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Merge Tailwind CSS classes with proper precedence handling.
 *
 * Combines clsx for conditional classes and tailwind-merge
 * for resolving conflicting Tailwind utilities.
 *
 * @param inputs - Class values to merge (strings, objects, arrays)
 * @returns Merged class string
 *
 * @example
 * ```ts
 * cn('px-2 py-1', 'px-4') // => 'py-1 px-4'
 * cn('text-red-500', isActive && 'text-blue-500')
 * ```
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
