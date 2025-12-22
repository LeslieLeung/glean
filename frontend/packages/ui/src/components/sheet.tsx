'use client'

import { Dialog as SheetPrimitive } from '@base-ui-components/react/dialog'
import { XIcon } from 'lucide-react'
import { cn } from '../utils'
import { ScrollArea } from './scroll-area'

const Sheet = SheetPrimitive.Root

const SheetPortal = SheetPrimitive.Portal

function SheetTrigger(props: SheetPrimitive.Trigger.Props) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />
}

function SheetClose(props: SheetPrimitive.Close.Props) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />
}

function SheetBackdrop({ className, ...props }: SheetPrimitive.Backdrop.Props) {
  return (
    <SheetPrimitive.Backdrop
      className={cn(
        'fixed inset-0 z-50 bg-black/32 backdrop-blur-sm transition-all duration-200 data-ending-style:opacity-0 data-starting-style:opacity-0',
        className
      )}
      data-slot="sheet-backdrop"
      {...props}
    />
  )
}

function SheetViewport({
  className,
  side,
  inset = false,
  ...props
}: SheetPrimitive.Viewport.Props & {
  side?: 'right' | 'left' | 'top' | 'bottom'
  inset?: boolean
}) {
  return (
    <SheetPrimitive.Viewport
      className={cn(
        'fixed inset-0 z-50 grid',
        side === 'bottom' && 'grid grid-rows-[1fr_auto] pt-12',
        side === 'top' && 'grid grid-rows-[auto_1fr] pb-12',
        side === 'left' && 'flex justify-start',
        side === 'right' && 'flex justify-end',
        inset && 'sm:p-4',
        className
      )}
      data-slot="sheet-viewport"
      {...props}
    />
  )
}

function SheetPopup({
  className,
  children,
  showCloseButton = true,
  side = 'right',
  inset = false,
  ...props
}: SheetPrimitive.Popup.Props & {
  showCloseButton?: boolean
  side?: 'right' | 'left' | 'top' | 'bottom'
  inset?: boolean
}) {
  return (
    <SheetPortal>
      <SheetBackdrop />
      <SheetViewport inset={inset} side={side}>
        <SheetPrimitive.Popup
          className={cn(
            'bg-popover text-popover-foreground relative flex max-h-full min-h-0 w-full min-w-0 flex-col bg-clip-padding shadow-lg transition-[opacity,translate] duration-200 ease-in-out will-change-transform before:pointer-events-none before:absolute before:inset-0 before:shadow-[0_1px_--theme(--color-black/4%)] data-ending-style:opacity-0 data-starting-style:opacity-0 max-sm:before:hidden dark:bg-clip-border dark:before:shadow-[0_-1px_--theme(--color-white/8%)]',
            side === 'bottom' &&
              'row-start-2 border-t data-ending-style:translate-y-8 data-starting-style:translate-y-8',
            side === 'top' &&
              'border-b data-ending-style:-translate-y-8 data-starting-style:-translate-y-8',
            side === 'left' &&
              'w-[calc(100%-(--spacing(12)))] max-w-md border-e data-ending-style:-translate-x-8 data-starting-style:-translate-x-8',
            side === 'right' &&
              'col-start-2 w-[calc(100%-(--spacing(12)))] max-w-md border-s data-ending-style:translate-x-8 data-starting-style:translate-x-8',
            inset &&
              'before:hidden sm:rounded-2xl sm:border sm:before:rounded-[calc(var(--radius-2xl)-1px)] sm:**:data-[slot=sheet-footer]:rounded-b-xl',
            className
          )}
          data-slot="sheet-popup"
          {...props}
        >
          {children}
          {showCloseButton && (
            <SheetPrimitive.Close className="focus-visible:ring-ring focus-visible:ring-offset-background absolute end-2 top-2 inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md border border-transparent opacity-72 transition-[color,background-color,box-shadow,opacity] outline-none hover:opacity-100 focus-visible:ring-2 focus-visible:ring-offset-1 pointer-coarse:after:absolute pointer-coarse:after:size-full pointer-coarse:after:min-h-11 pointer-coarse:after:min-w-11 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4">
              <XIcon />
              <span className="sr-only">Close</span>
            </SheetPrimitive.Close>
          )}
        </SheetPrimitive.Popup>
      </SheetViewport>
    </SheetPortal>
  )
}

function SheetHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        'flex flex-col gap-2 p-6 in-[[data-slot=sheet-popup]:has([data-slot=sheet-panel])]:pb-3 max-sm:pb-4',
        className
      )}
      data-slot="sheet-header"
      {...props}
    />
  )
}

function SheetFooter({
  className,
  variant = 'default',
  ...props
}: React.ComponentProps<'div'> & {
  variant?: 'default' | 'bare'
}) {
  return (
    <div
      className={cn(
        'flex flex-col-reverse gap-2 px-6 sm:flex-row sm:justify-end',
        variant === 'default' && 'bg-muted/50 border-t py-4',
        variant === 'bare' &&
          'pt-4 pb-6 in-[[data-slot=sheet-popup]:has([data-slot=sheet-panel])]:pt-3',
        className
      )}
      data-slot="sheet-footer"
      {...props}
    />
  )
}

function SheetTitle({ className, ...props }: SheetPrimitive.Title.Props) {
  return (
    <SheetPrimitive.Title
      className={cn('font-heading text-xl leading-none', className)}
      data-slot="sheet-title"
      {...props}
    />
  )
}

function SheetDescription({ className, ...props }: SheetPrimitive.Description.Props) {
  return (
    <SheetPrimitive.Description
      className={cn('text-muted-foreground text-sm', className)}
      data-slot="sheet-description"
      {...props}
    />
  )
}

function SheetPanel({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <ScrollArea>
      <div
        className={cn(
          'px-6 pb-6 in-[[data-slot=sheet-popup]:has([data-slot=sheet-header])]:pt-1 in-[[data-slot=sheet-popup]:not(:has([data-slot=sheet-footer]))]:pb-6! in-[[data-slot=sheet-popup]:not(:has([data-slot=sheet-footer].border-t))]:pb-1 in-[[data-slot=sheet-popup]:not(:has([data-slot=sheet-header]))]:pt-6',
          className
        )}
        data-slot="sheet-panel"
        {...props}
      />
    </ScrollArea>
  )
}

export {
  Sheet,
  SheetTrigger,
  SheetPortal,
  SheetClose,
  SheetBackdrop,
  SheetBackdrop as SheetOverlay,
  SheetPopup,
  SheetPopup as SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
  SheetPanel,
}
