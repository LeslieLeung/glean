'use client'

import { Switch as SwitchPrimitive } from '@base-ui-components/react/switch'

import { cn } from '../utils'

function Switch({ className, ...props }: SwitchPrimitive.Root.Props) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        'group/switch focus-visible:ring-ring focus-visible:ring-offset-background data-checked:bg-primary data-unchecked:bg-input inline-flex h-4.5 w-7.5 shrink-0 items-center rounded-full p-px inset-shadow-[0_1px_--theme(--color-black/4%)] transition-all outline-none focus-visible:ring-2 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-64',
        className
      )}
      data-slot="switch"
      {...props}
    >
      <SwitchPrimitive.Thumb
        className={cn(
          'bg-background pointer-events-none block size-4 rounded-full shadow-sm transition-[translate,width] group-active/switch:w-4.5 data-checked:translate-x-3 data-checked:group-active/switch:translate-x-2.5 data-unchecked:translate-x-0'
        )}
        data-slot="switch-thumb"
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
