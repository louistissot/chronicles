import * as React from "react"
import { cn } from "@/lib/utils"

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full rounded-md border border-white/10 bg-shadow px-3 py-1 text-sm text-parchment shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-parchment/30 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold/60 focus-visible:border-gold/50 disabled:cursor-not-allowed disabled:opacity-50 font-body",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
