import { ChevronDown, type LucideIcon } from "lucide-react";

export interface NexusSelectOption {
  value: string;
  label: string;
  badge?: string;
}

export interface NexusSelectProps {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<NexusSelectOption | string>;
  icon?: LucideIcon;
  className?: string;
  selectClassName?: string;
  fullWidth?: boolean;
  disabled?: boolean;
  ariaLabel?: string;
}

export function NexusSelect({
  label,
  value,
  onChange,
  options,
  icon: Icon,
  className = "",
  selectClassName = "",
  fullWidth = false,
  disabled = false,
  ariaLabel,
}: NexusSelectProps) {
  const normalizedOptions: NexusSelectOption[] = options.map((opt) =>
    typeof opt === "string" ? { value: opt, label: opt } : opt,
  );

  return (
    <div className={`flex flex-col gap-1 ${fullWidth ? "w-full" : "inline-flex"} ${className}`}>
      {label && (
        <label className="font-mono text-[10px] uppercase tracking-wider text-slate-400 select-none">
          {label}
        </label>
      )}
      <div className="relative w-full">
        {Icon && (
          <Icon className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-cyan-400" />
        )}
        <select
          value={value}
          disabled={disabled}
          aria-label={ariaLabel || label}
          onChange={(e) => onChange(e.target.value)}
          className={`appearance-none w-full rounded-md border border-cyan-500/35 bg-[#030712] py-1.5 font-mono text-xs text-cyan-200 shadow-inner transition-all hover:border-cyan-400/60 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/40 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer ${
            Icon ? "pl-8" : "pl-3"
          } pr-8 ${selectClassName}`}
        >
          {normalizedOptions.map((opt) => (
            <option
              key={opt.value}
              value={opt.value}
              className="bg-[#030712] text-slate-100 font-mono text-xs py-1"
            >
              {opt.label} {opt.badge ? `(${opt.badge})` : ""}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-cyan-400/80 transition-transform group-hover:text-cyan-300" />
      </div>
    </div>
  );
}
