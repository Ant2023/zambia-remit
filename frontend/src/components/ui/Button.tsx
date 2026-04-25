import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type ButtonVariant = "primary" | "accent" | "secondary";
type ButtonSize = "sm" | "md" | "lg";

const variantClasses: Record<ButtonVariant, string> = {
  primary: "mbp-button-primary",
  accent: "mbp-button-accent",
  secondary: "mbp-button-secondary",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "min-h-10 px-4 py-2 text-sm",
  md: "min-h-12 px-5 py-3 text-sm",
  lg: "min-h-14 px-6 py-4 text-base",
};

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
};

export function Button({
  className,
  variant = "primary",
  size = "md",
  fullWidth = false,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        variantClasses[variant],
        sizeClasses[size],
        fullWidth && "w-full",
        className,
      )}
      type={type}
      {...props}
    />
  );
}
