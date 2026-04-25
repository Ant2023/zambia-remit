import type { InputHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  helperText?: ReactNode;
  error?: ReactNode;
};

export function Input({
  className,
  id,
  label,
  helperText,
  error,
  ...props
}: InputProps) {
  const input = (
    <input
      aria-describedby={
        error ? `${id}-error` : helperText ? `${id}-helper` : undefined
      }
      aria-invalid={Boolean(error) || undefined}
      className={cn(
        "mbp-input",
        Boolean(error) && "border-red-300 focus:border-red-500 focus:ring-red-100",
        className,
      )}
      id={id}
      {...props}
    />
  );

  if (!label) {
    return input;
  }

  return (
    <label className="mbp-label" htmlFor={id}>
      <span>{label}</span>
      {input}
      {helperText && !error ? (
        <span className="mbp-helper-text" id={`${id}-helper`}>
          {helperText}
        </span>
      ) : null}
      {error ? (
        <span className="text-sm font-semibold text-mbongo-error" id={`${id}-error`}>
          {error}
        </span>
      ) : null}
    </label>
  );
}
