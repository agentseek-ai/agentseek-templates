import type { RunMode } from "./contracts";

type ModeSwitchProps = {
  mode: RunMode;
  disabled: boolean;
  onChange: (mode: RunMode) => void;
};

export function ModeSwitch({ mode, disabled, onChange }: ModeSwitchProps) {
  return (
    <fieldset disabled={disabled} aria-label="Run mode">
      <legend>Run mode</legend>
      <label>
        <input
          type="radio"
          name="run-mode"
          value="demo"
          disabled={disabled}
          checked={mode === "demo"}
          onChange={() => {
            if (!disabled) onChange("demo");
          }}
        />
        Guided Demo · no key
      </label>
      <label>
        <input
          type="radio"
          name="run-mode"
          value="live"
          disabled={disabled}
          checked={mode === "live"}
          onChange={() => {
            if (!disabled) onChange("live");
          }}
        />
        Live Model · uses server configuration
      </label>
    </fieldset>
  );
}
