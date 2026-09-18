import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Language = "en" | "zh";

const STORAGE_KEY = "powercontext.language";

const en = {
  "app.eyebrow": "Deep Agents + PowerContext",
  "app.lede":
    "New conversation. Same project knowledge. Save a release decision, start fresh, and watch your agents pick it up from PowerContext.",
  "app.emptyHint":
    "Try: “{question}” Then turn recall off and ask the same question in a fresh conversation.",
  "language.switch": "中文",
  "language.ariaToZh": "Switch the interface to Chinese",
  "language.ariaToEn": "Switch the interface to English",
  "session.eyebrow": "02 · Start fresh",
  "session.threadActive": "Thread active",
  "session.threadReady": "Thread ready",
  "session.threadActiveHint": "Your next request continues this conversation.",
  "session.threadReadyHint": "Your next request starts a fresh conversation. Project memory is kept.",
  "session.newConversation": "New conversation",
  "session.recall": "Recall project memory",
  "session.budget": "Context budget",
  "session.bytes512": "512 bytes",
  "session.bytes2000": "2,000 bytes",
  "session.bytes8000": "8,000 bytes",
  "session.hint":
    "Changing recall or its budget starts a fresh conversation for comparison. The backend may apply a lower configured budget.",
  "plan.eyebrow": "03 · Recall and inspect",
  "plan.heading": "Plan the next release",
  "plan.tryDemo": "Try release question",
  "composer.messageLabel": "Message",
  "composer.placeholder": "Ask about your project's release…",
  "composer.send": "Send",
  "activity.streaming": "Streaming the run…",
  "demo.question": "What is the release plan for Project Phoenix?",
  "demo.memory":
    "Project Phoenix release: deploy to the Singapore region on Tuesday at 10:00 UTC. Require Mei's approval and a tested rollback before release.",
  "memory.aria": "Project memory",
  "memory.eyebrow": "01 · Remember",
  "memory.heading": "Project decisions",
  "memory.refresh": "Refresh memory",
  "memory.intro":
    "Save a decision here. It stays in PowerContext when you start a new conversation or restart this app.",
  "memory.create": "Create project memory",
  "memory.textLabel": "Decision to keep across conversations",
  "memory.save": "Save decision",
  "memory.useExample": "Use example decision",
  "memory.empty": "No saved decisions yet. Save the example to try cross-conversation recall.",
  "memory.savedEvidence": "Saved evidence · version {version}",
  "memory.scope": "Project scope",
  "memory.connecting": "Connecting to PowerContext…",
  "memory.ready": "Project memory is ready.",
  "memory.saved": "Saved to PowerContext · entry version {version}.",
  "memory.savedNoEntry":
    "PowerContext accepted the write without an entry receipt. Refresh to inspect it.",
  "memory.loadError": "Could not load project memory.",
  "memory.requestError": "Memory request failed.",
  "memory.unconfirmed": "Memory operation was not confirmed.",
  "timeline.aria": "Answer and recalled context",
  "timeline.source.coordinator": "coordinator",
  "timeline.source.subagent": "subagent",
  "timeline.source.agent": "agent",
  "timeline.message": "answer",
  "timeline.streamError": "stream · error",
  "timeline.bytesPrepared": "{bytes} UTF-8 bytes prepared",
  "timeline.empty":
    "No relevant memory fit this query and budget. Try matching project terms or increasing the budget.",
  "timeline.disabled": "Recall is off for this run.",
  "timeline.unavailable":
    "Project memory could not be reached. The agent continues without recalled context.",
  "timeline.contextSummary": "Context supplied to this model call",
  "timeline.contextNote":
    "Historical evidence; current instructions take precedence. This context is not saved in conversation history.",
} as const;

export type MessageKey = keyof typeof en;

const zh: Record<MessageKey, string> = {
  "app.eyebrow": "Deep Agents + PowerContext",
  "app.lede":
    "开启新会话，项目知识依旧。保存一条发布决策，开启全新对话，看看智能体如何从 PowerContext 中取回它。",
  "app.emptyHint": "试试：“{question}” 然后关闭召回，在新会话中提出同一个问题。",
  "language.switch": "English",
  "language.ariaToZh": "将界面切换为中文",
  "language.ariaToEn": "将界面切换为英文",
  "session.eyebrow": "02 · 开启新会话",
  "session.threadActive": "会话进行中",
  "session.threadReady": "会话已就绪",
  "session.threadActiveHint": "你的下一条消息会延续当前会话。",
  "session.threadReadyHint": "你的下一次提问会开启全新会话，项目记忆仍会保留。",
  "session.newConversation": "新会话",
  "session.recall": "召回项目记忆",
  "session.budget": "上下文预算",
  "session.bytes512": "512 字节",
  "session.bytes2000": "2,000 字节",
  "session.bytes8000": "8,000 字节",
  "session.hint": "切换召回开关或预算会开启新的对比会话。后端可能应用更低的配置预算。",
  "plan.eyebrow": "03 · 召回与检查",
  "plan.heading": "规划下一次发布",
  "plan.tryDemo": "试用发布问题",
  "composer.messageLabel": "消息",
  "composer.placeholder": "询问你的项目发布计划…",
  "composer.send": "发送",
  "activity.streaming": "正在流式输出…",
  "demo.question": "Project Phoenix 的发布计划是什么？",
  "demo.memory":
    "Project Phoenix 发布：周二 10:00 UTC 部署到新加坡区域。发布前需要 Mei 审批并通过回滚测试。",
  "memory.aria": "项目记忆",
  "memory.eyebrow": "01 · 记住",
  "memory.heading": "项目决策",
  "memory.refresh": "刷新记忆",
  "memory.intro": "在这里保存一条决策。开启新会话或重启应用后，它仍会保留在 PowerContext 中。",
  "memory.create": "创建项目记忆",
  "memory.textLabel": "希望跨会话保留的决策",
  "memory.save": "保存决策",
  "memory.useExample": "使用示例决策",
  "memory.empty": "还没有保存的决策。保存示例即可体验跨会话召回。",
  "memory.savedEvidence": "已保存的证据 · 版本 {version}",
  "memory.scope": "项目 Scope",
  "memory.connecting": "正在连接 PowerContext…",
  "memory.ready": "项目记忆已就绪。",
  "memory.saved": "已保存到 PowerContext · 条目版本 {version}。",
  "memory.savedNoEntry": "PowerContext 已接受写入，但没有返回条目回执。请刷新查看。",
  "memory.loadError": "无法加载项目记忆。",
  "memory.requestError": "记忆请求失败。",
  "memory.unconfirmed": "记忆操作未确认。",
  "timeline.aria": "回答与召回的上下文",
  "timeline.source.coordinator": "协调者",
  "timeline.source.subagent": "子代理",
  "timeline.source.agent": "智能体",
  "timeline.message": "回答",
  "timeline.streamError": "流 · 错误",
  "timeline.bytesPrepared": "已准备 {bytes} UTF-8 字节",
  "timeline.empty": "没有匹配的记忆内容符合本次查询与预算。请尝试匹配项目关键词或提高预算。",
  "timeline.disabled": "本次运行已关闭召回。",
  "timeline.unavailable": "无法访问项目记忆，智能体将在没有召回上下文的情况下继续。",
  "timeline.contextSummary": "提供给本次模型调用的上下文",
  "timeline.contextNote": "历史证据；当前指令优先。此上下文不会写入会话历史。",
};

export const messages: Record<Language, Record<MessageKey, string>> = { en, zh };

type Vars = Record<string, string | number>;

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match,
  );
}

export type I18n = {
  language: Language;
  setLanguage: (language: Language) => void;
  toggleLanguage: () => void;
  t: (key: MessageKey, vars?: Vars) => string;
};

const fallback: I18n = {
  language: "en",
  setLanguage: () => undefined,
  toggleLanguage: () => undefined,
  t: (key, vars) => interpolate(en[key], vars),
};

const I18nContext = createContext<I18n>(fallback);

export function detectLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "zh") return stored;
  } catch {
    // Storage can be unavailable in privacy-restricted browsers; fall back to the locale.
  }
  const preferred = typeof navigator === "undefined" ? "" : navigator.language ?? "";
  return preferred.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export function I18nProvider({
  children,
  initialLanguage,
}: {
  children: ReactNode;
  initialLanguage?: Language;
}) {
  const [language, setLanguage] = useState<Language>(() => initialLanguage ?? detectLanguage());

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    try {
      window.localStorage.setItem(STORAGE_KEY, language);
    } catch {
      // Persisting the choice is a convenience; the current session still switches.
    }
  }, [language]);

  const toggleLanguage = useCallback(
    () => setLanguage((current) => (current === "en" ? "zh" : "en")),
    [],
  );

  const value = useMemo<I18n>(
    () => ({
      language,
      setLanguage,
      toggleLanguage,
      t: (key, vars) => interpolate(messages[language][key] ?? en[key], vars),
    }),
    [language, toggleLanguage],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  return useContext(I18nContext);
}
