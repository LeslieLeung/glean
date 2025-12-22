'use client'

import { Combobox as ComboboxPrimitive } from '@base-ui-components/react/combobox'
import { ChevronsUpDownIcon, XIcon } from 'lucide-react'
import * as React from 'react'

import { cn } from '../utils'
import { Input } from './Input'
import { ScrollArea } from './scroll-area'

const ComboboxContext = React.createContext<{
  chipsRef: React.RefObject<HTMLDivElement> | null
  multiple: boolean
}>({
  chipsRef: null,
  multiple: false,
})

type ComboboxRootProps<ItemValue, Multiple extends boolean | undefined> = Parameters<
  typeof ComboboxPrimitive.Root<ItemValue, Multiple>
>[0]

function Combobox<ItemValue, Multiple extends boolean | undefined = false>(
  props: ComboboxPrimitive.Root.Props<ItemValue, Multiple>
) {
  const chipsRef = React.useRef<HTMLDivElement>(null)
  return (
    <ComboboxContext.Provider value={{ chipsRef, multiple: !!props.multiple }}>
      <ComboboxPrimitive.Root {...(props as ComboboxRootProps<ItemValue, Multiple>)} />
    </ComboboxContext.Provider>
  )
}

function ComboboxInput({
  className,
  showTrigger = true,
  showClear = false,
  size,
  ...props
}: Omit<ComboboxPrimitive.Input.Props, 'size'> & {
  showTrigger?: boolean
  showClear?: boolean
  size?: 'sm' | 'default' | 'lg' | number
}) {
  const { multiple } = React.useContext(ComboboxContext)
  const sizeValue = (size ?? 'default') as 'sm' | 'default' | 'lg' | number

  // multiple mode
  if (multiple) {
    return (
      <ComboboxPrimitive.Input
        className={cn(
          'min-w-12 flex-1 text-base/5 outline-none sm:text-sm [[data-slot=combobox-chip]+&]:ps-0.5',
          sizeValue === 'sm' ? 'ps-1.5' : 'ps-2',
          className
        )}
        data-size={typeof sizeValue === 'string' ? sizeValue : undefined}
        data-slot="combobox-input"
        size={typeof sizeValue === 'number' ? sizeValue : undefined}
        {...props}
      />
    )
  }
  // single mode
  return (
    <div className="relative w-full has-disabled:opacity-64">
      <ComboboxPrimitive.Input
        className={cn(
          sizeValue === 'sm'
            ? 'has-[+[data-slot=combobox-trigger],+[data-slot=combobox-clear]]:*:data-[slot=combobox-input]:pe-6.5'
            : 'has-[+[data-slot=combobox-trigger],+[data-slot=combobox-clear]]:*:data-[slot=combobox-input]:pe-7',
          className
        )}
        data-slot="combobox-input"
        render={<Input className="has-disabled:opacity-100" size={sizeValue} />}
        {...props}
      />
      {showTrigger && (
        <ComboboxTrigger
          className={cn(
            "absolute top-1/2 inline-flex size-7 shrink-0 -translate-y-1/2 cursor-pointer items-center justify-center rounded-md border border-transparent opacity-72 transition-opacity outline-none hover:opacity-100 has-[+[data-slot=combobox-clear]]:hidden pointer-coarse:after:absolute pointer-coarse:after:min-h-11 pointer-coarse:after:min-w-11 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
            sizeValue === 'sm' ? 'end-0' : 'end-0.5'
          )}
        >
          <ChevronsUpDownIcon />
        </ComboboxTrigger>
      )}
      {showClear && (
        <ComboboxClear
          className={cn(
            "absolute top-1/2 inline-flex size-7 shrink-0 -translate-y-1/2 cursor-pointer items-center justify-center rounded-md border border-transparent opacity-72 transition-opacity outline-none hover:opacity-100 has-[+[data-slot=combobox-clear]]:hidden pointer-coarse:after:absolute pointer-coarse:after:min-h-11 pointer-coarse:after:min-w-11 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
            sizeValue === 'sm' ? 'end-0' : 'end-0.5'
          )}
        >
          <XIcon />
        </ComboboxClear>
      )}
    </div>
  )
}

function ComboboxTrigger({ className, ...props }: ComboboxPrimitive.Trigger.Props) {
  return <ComboboxPrimitive.Trigger className={className} data-slot="combobox-trigger" {...props} />
}

function ComboboxPopup({
  className,
  children,
  sideOffset = 4,
  ...props
}: ComboboxPrimitive.Popup.Props & {
  sideOffset?: number
}) {
  const { chipsRef } = React.useContext(ComboboxContext)

  return (
    <ComboboxPrimitive.Portal>
      <ComboboxPrimitive.Positioner
        anchor={chipsRef}
        className="z-50 select-none"
        data-slot="combobox-positioner"
        sideOffset={sideOffset}
      >
        <span
          className={cn(
            'bg-popover relative flex max-h-full origin-(--transform-origin) rounded-lg border bg-clip-padding transition-[scale,opacity] before:pointer-events-none before:absolute before:inset-0 before:rounded-[calc(var(--radius-lg)-1px)] before:shadow-lg has-data-starting-style:scale-98 has-data-starting-style:opacity-0 dark:not-in-data-[slot=group]:bg-clip-border',
            className
          )}
        >
          <ComboboxPrimitive.Popup
            className="flex max-h-[min(var(--available-height),23rem)] w-(--anchor-width) max-w-(--available-width) flex-col"
            data-slot="combobox-popup"
            {...props}
          >
            {children}
          </ComboboxPrimitive.Popup>
        </span>
      </ComboboxPrimitive.Positioner>
    </ComboboxPrimitive.Portal>
  )
}

function ComboboxItem({ className, children, ...props }: ComboboxPrimitive.Item.Props) {
  return (
    <ComboboxPrimitive.Item
      className={cn(
        "data-highlighted:bg-accent data-highlighted:text-accent-foreground grid cursor-default grid-cols-[1rem_1fr] items-center gap-2 rounded-sm py-1 ps-2 pe-4 text-base outline-none in-data-[side=none]:min-w-[calc(var(--anchor-width)+1.25rem)] data-disabled:pointer-events-none data-disabled:opacity-64 sm:text-sm [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      data-slot="combobox-item"
      {...props}
    >
      <ComboboxPrimitive.ItemIndicator className="col-start-1">
        <svg
          fill="none"
          height="24"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
          viewBox="0 0 24 24"
          width="24"
          xmlns="http://www.w3.org/1500/svg"
        >
          <path d="M5.252 12.7 10.2 18.63 18.748 5.37" />
        </svg>
      </ComboboxPrimitive.ItemIndicator>
      <div className="col-start-2">{children}</div>
    </ComboboxPrimitive.Item>
  )
}

function ComboboxSeparator({ className, ...props }: ComboboxPrimitive.Separator.Props) {
  return (
    <ComboboxPrimitive.Separator
      className={cn('bg-border mx-2 my-1 h-px last:hidden', className)}
      data-slot="combobox-separator"
      {...props}
    />
  )
}

function ComboboxGroup({ className, ...props }: ComboboxPrimitive.Group.Props) {
  return <ComboboxPrimitive.Group className={className} data-slot="combobox-group" {...props} />
}

function ComboboxGroupLabel({ className, ...props }: ComboboxPrimitive.GroupLabel.Props) {
  return (
    <ComboboxPrimitive.GroupLabel
      className={cn('text-muted-foreground px-2 py-1.5 text-xs font-medium', className)}
      data-slot="combobox-group-label"
      {...props}
    />
  )
}

function ComboboxEmpty({ className, ...props }: ComboboxPrimitive.Empty.Props) {
  return (
    <ComboboxPrimitive.Empty
      className={cn('text-muted-foreground text-center text-sm not-empty:p-2', className)}
      data-slot="combobox-empty"
      {...props}
    />
  )
}

function ComboboxRow({ className, ...props }: ComboboxPrimitive.Row.Props) {
  return <ComboboxPrimitive.Row className={className} data-slot="combobox-row" {...props} />
}

function ComboboxValue({ ...props }: ComboboxPrimitive.Value.Props) {
  return <ComboboxPrimitive.Value data-slot="combobox-value" {...props} />
}

function ComboboxList({ className, ...props }: ComboboxPrimitive.List.Props) {
  return (
    <ScrollArea className="flex-1">
      <ComboboxPrimitive.List
        className={cn(
          'not-empty:scroll-py-1 not-empty:px-1 not-empty:py-1 in-data-has-overflow-y:pe-3',
          className
        )}
        data-slot="combobox-list"
        {...props}
      />
    </ScrollArea>
  )
}

function ComboboxClear({ className, ...props }: ComboboxPrimitive.Clear.Props) {
  return <ComboboxPrimitive.Clear className={className} data-slot="combobox-clear" {...props} />
}

function ComboboxStatus({ className, ...props }: ComboboxPrimitive.Status.Props) {
  return (
    <ComboboxPrimitive.Status
      className={cn(
        'text-muted-foreground px-3 py-2 text-xs font-medium empty:m-0 empty:p-0',
        className
      )}
      data-slot="combobox-status"
      {...props}
    />
  )
}

function ComboboxCollection(props: ComboboxPrimitive.Collection.Props) {
  return <ComboboxPrimitive.Collection data-slot="combobox-collection" {...props} />
}

function ComboboxChips({ className, ...props }: ComboboxPrimitive.Chips.Props) {
  const { chipsRef } = React.useContext(ComboboxContext)

  return (
    <ComboboxPrimitive.Chips
      className={cn(
        'border-input bg-background ring-ring/24 focus-within:border-ring has-aria-invalid:border-destructive/36 focus-within:has-aria-invalid:border-destructive/64 focus-within:has-aria-invalid:ring-destructive/16 dark:not-has-disabled:bg-input/32 dark:has-aria-invalid:ring-destructive/24 relative inline-flex min-h-8 w-full flex-wrap gap-1 rounded-lg border bg-clip-padding p-[calc(--spacing(1)-1px)] text-base/5 shadow-xs transition-shadow outline-none *:min-h-6 before:pointer-events-none before:absolute before:inset-0 before:rounded-[calc(var(--radius-lg)-1px)] not-has-disabled:not-focus-within:not-aria-invalid:before:shadow-[0_1px_--theme(--color-black/4%)] focus-within:ring-[3px] has-disabled:pointer-events-none has-disabled:opacity-64 has-data-[size=lg]:min-h-9 has-data-[size=lg]:*:min-h-7 has-data-[size=sm]:min-h-7 has-data-[size=sm]:*:min-h-5 has-[:disabled,:focus-within,[aria-invalid]]:shadow-none sm:text-sm dark:not-in-data-[slot=group]:bg-clip-border dark:not-has-disabled:not-focus-within:not-aria-invalid:before:shadow-[0_-1px_--theme(--color-white/8%)]',
        className
      )}
      data-slot="combobox-chips"
      ref={chipsRef}
      {...props}
    />
  )
}

function ComboboxChip({ children, ...props }: ComboboxPrimitive.Chip.Props) {
  return (
    <ComboboxPrimitive.Chip
      className="bg-accent text-accent-foreground flex items-center rounded-[calc(var(--radius-md)-1px)] ps-2 text-xs font-medium outline-none"
      data-slot="combobox-chip"
      {...props}
    >
      {children}
      <ComboboxChipRemove />
    </ComboboxPrimitive.Chip>
  )
}

function ComboboxChipRemove(props: ComboboxPrimitive.ChipRemove.Props) {
  return (
    <ComboboxPrimitive.ChipRemove
      aria-label="Remove"
      className="h-full shrink-0 cursor-pointer px-1.5 opacity-72 hover:opacity-100 [&_svg:not([class*='size-'])]:size-3.5"
      data-slot="combobox-chip-remove"
      {...props}
    >
      <XIcon />
    </ComboboxPrimitive.ChipRemove>
  )
}

export {
  Combobox,
  ComboboxInput,
  ComboboxTrigger,
  ComboboxPopup,
  ComboboxItem,
  ComboboxSeparator,
  ComboboxGroup,
  ComboboxGroupLabel,
  ComboboxEmpty,
  ComboboxValue,
  ComboboxList,
  ComboboxClear,
  ComboboxStatus,
  ComboboxRow,
  ComboboxCollection,
  ComboboxChips,
  ComboboxChip,
}
