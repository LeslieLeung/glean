'use client'

import { Avatar as AvatarPrimitive } from '@base-ui-components/react/avatar'

import { cn } from '../utils'

function Avatar({ className, ...props }: AvatarPrimitive.Root.Props) {
  return (
    <AvatarPrimitive.Root
      className={cn(
        'bg-background inline-flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full align-middle text-xs font-medium select-none',
        className
      )}
      data-slot="avatar"
      {...props}
    />
  )
}

function AvatarImage({ className, ...props }: AvatarPrimitive.Image.Props) {
  return (
    <AvatarPrimitive.Image
      className={cn('size-full object-cover', className)}
      data-slot="avatar-image"
      {...props}
    />
  )
}

function AvatarFallback({ className, ...props }: AvatarPrimitive.Fallback.Props) {
  return (
    <AvatarPrimitive.Fallback
      className={cn('bg-muted flex size-full items-center justify-center rounded-full', className)}
      data-slot="avatar-fallback"
      {...props}
    />
  )
}

export { Avatar, AvatarImage, AvatarFallback }
