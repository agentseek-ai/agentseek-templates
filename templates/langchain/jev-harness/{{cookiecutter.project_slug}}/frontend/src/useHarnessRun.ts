import { useRef, useState } from "react";
import { useStream } from "@langchain/react";
import { HarnessState, Message, messageText } from "./harness";

/** One hook owns one conversation; Arena mounts two independent hooks. */
export function useHarnessRun() {
  const stream = useStream<HarnessState>({
    apiUrl: import.meta.env.VITE_LANGGRAPH_API_URL ?? "http://127.0.0.1:{{ cookiecutter.langgraph_port }}",
    assistantId: "agent",
  });
  const inFlight = useRef(false);
  const [pending, setPending] = useState(false);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [requestError, setRequestError] = useState<unknown>(null);
  const messages = stream.messages as Message[];

  async function start(content: string, proposal: string, model: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setRequestError(null);
    setElapsed(null);
    const started = performance.now();
    try {
      await stream.submit(
        { messages: [{ type: "human", content }], proposal_id: proposal },
        { config: { recursion_limit: 24, configurable: { decision_model: model } } },
      );
    } catch (error) {
      // A failed participant must not cancel or hide the other participant.
      setRequestError(error);
    } finally {
      setElapsed(performance.now() - started);
      setPending(false);
      inFlight.current = false;
    }
  }

  return {
    start, elapsed, error: requestError ?? stream.error,
    isLoading: pending || stream.isLoading,
    route: stream.values.route_report,
    tools: messages.filter(message => message.type === "tool"),
    answers: messages.filter(message => message.type === "ai" && messageText(message.content)),
  };
}
export type HarnessRun = ReturnType<typeof useHarnessRun>;
