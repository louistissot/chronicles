import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 font-body",
  {
    variants: {
      variant: {
        default:
          "bg-gold text-void shadow-[0_0_12px_rgba(212,175,55,0.4)] hover:bg-gold-light hover:shadow-[0_0_20px_rgba(212,175,55,0.6)] active:bg-gold-dark border border-gold/30",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        outline:
          "border border-gold/40 bg-transparent text-gold shadow-sm hover:bg-gold/10 hover:border-gold/70 hover:shadow-[0_0_12px_rgba(212,175,55,0.2)]",
        secondary:
          "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80 border border-white/10",
        ghost:
          "text-parchment/70 hover:bg-white/5 hover:text-parchment",
        link:
          "text-gold underline-offset-4 hover:underline",
        arcane:
          "bg-arcane text-white shadow-[0_0_12px_rgba(124,58,237,0.4)] hover:bg-arcane-light hover:shadow-[0_0_20px_rgba(124,58,237,0.6)] active:bg-arcane-dark border border-arcane/30",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-11 rounded-md px-8 text-base",
        xl: "h-13 rounded-lg px-10 text-lg",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
