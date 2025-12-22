'use client'

import { Radio as RadioPrimitive } from '@base-ui-components/react/radio'
import { RadioGroup as RadioGroupPrimitive } from '@base-ui-components/react/radio-group'

import { cn } from '../utils'

function RadioGroup({ className, ...props }: RadioGroupPrimitive.Props) {
  return (
    <RadioGroupPrimitive
      className={cn('flex flex-col gap-3', className)}
      data-slot="radio-group"
      {...props}
    />
  )
}

function Radio({ className, ...props }: RadioPrimitive.Root.Props) {
  return (
    <RadioPrimitive.Root
      className={cn(
        'border-input bg-background focus-visible:ring-ring focus-visible:ring-offset-background aria-invalid:border-destructive/36 focus-visible:aria-invalid:border-destructive/64 focus-visible:aria-invalid:ring-destructive/48 dark:not-data-checked:bg-input/32 dark:aria-invalid:ring-destructive/24 relative inline-flex size-4 shrink-0 items-center justify-center rounded-full border bg-clip-padding shadow-xs transition-shadow outline-none before:pointer-events-none before:absolute before:inset-0 before:rounded-full not-data-disabled:not-data-checked:not-aria-invalid:before:shadow-[0_1px_--theme(--color-black/4%)] focus-visible:ring-2 focus-visible:ring-offset-1 data-disabled:cursor-not-allowed data-disabled:opacity-64 dark:bg-clip-border dark:not-data-disabled:not-data-checked:not-aria-invalid:before:shadow-[0_-1px_--theme(--color-white/8%)] [[data-disabled],[data-checked],[aria-invalid]]:shadow-none',
        className
      )}
      data-slot="radio"
      {...props}
    >
      <RadioPrimitive.Indicator
        className="before:bg-primary-foreground data-checked:bg-primary absolute -inset-px flex size-4 items-center justify-center rounded-full before:size-1.5 before:rounded-full data-unchecked:hidden"
        data-slot="radio-indicator"
      />
    </RadioPrimitive.Root>
  )
}

export { RadioGroup, Radio, Radio as RadioGroupItem }
