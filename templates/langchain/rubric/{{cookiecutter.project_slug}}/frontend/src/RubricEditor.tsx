import {
  MAX_ITERATIONS,
  TASK_PROMPT,
  type RunMode,
} from "./contracts";

type RubricEditorProps = {
  mode: RunMode;
  rubric: string;
  maxIterations: number;
  setRubric: (rubric: string) => void;
  setMaxIterations: (maxIterations: number) => void;
  resetBaseline: () => void;
  validationText: string | null;
};

export function RubricEditor({
  mode,
  rubric,
  maxIterations,
  setRubric,
  setMaxIterations,
  resetBaseline,
  validationText,
}: RubricEditorProps) {
  const readOnly = mode === "demo";
  return (
    <section aria-labelledby="rubric-editor-title">
      <h2 id="rubric-editor-title">Task and Rubric</h2>
      <label htmlFor="rubric-task">Task</label>
      <textarea id="rubric-task" value={TASK_PROMPT} readOnly rows={2} />

      <label htmlFor="rubric-text">Rubric</label>
      <textarea
        id="rubric-text"
        value={rubric}
        readOnly={readOnly}
        rows={9}
        onChange={(event) => setRubric(event.currentTarget.value)}
      />

      <label htmlFor="rubric-max-iterations">Maximum iterations</label>
      <input
        id="rubric-max-iterations"
        type="number"
        min={1}
        max={MAX_ITERATIONS}
        step={1}
        value={maxIterations}
        readOnly={readOnly}
        aria-describedby={validationText ? "rubric-validation" : undefined}
        aria-invalid={validationText ? true : undefined}
        onChange={(event) => {
          const value = Number(event.currentTarget.value);
          if (Number.isInteger(value)) setMaxIterations(value);
        }}
      />

      {mode === "live" ? (
        <button type="button" onClick={resetBaseline}>
          Reset baseline
        </button>
      ) : null}
      {validationText ? (
        <p id="rubric-validation" role="alert">
          {validationText}
        </p>
      ) : null}
    </section>
  );
}
