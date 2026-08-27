{% raw %}
export type PatternKind = "route" | "fan" | "verify" | "filter" | "tournament" | "loop";

export type PatternDefinition = {
  assistantId: string;
  kind: PatternKind;
  family: string;
  title: string;
  short: string;
  description: string;
  prompt: string;
  topologyLabel: string;
  topology: string[][];
  completion: string;
};

export const PATTERNS: PatternDefinition[] = [
  {
    assistantId: "classify_and_act",
    kind: "route",
    family: "Routing pattern",
    title: "Classify and act",
    short: "客服工单分诊",
    description:
      "先理解每条请求属于哪一类，再把它路由给最合适的专业角色。适合混合输入、不同类型需要不同处理方式的任务。",
    prompt: [
      "Run a workflow to classify and handle every customer request below.",
      "",
      "- C-101: Since yesterday, signing in with a correct password returns an unexpected 500 error.",
      "- C-102: We need a scheduled bulk export to our warehouse in Parquet format.",
      "- C-103: Does the annual plan include refunds for unused seats after a team member leaves?",
      "",
      "Return a concise triage table with the category, recommended action, and next step for each request.",
    ].join("\n"),
    topologyLabel: "classify → route → handle",
    topology: [["Customer requests"], ["Classify"], ["Bug path", "Feature path", "Support path"]],
    completion: "每条请求都得到分类、专业处理结果与下一步。",
  },
  {
    assistantId: "fan_out_and_synthesize",
    kind: "fan",
    family: "Parallel pattern",
    title: "Fan-out and synthesize",
    short: "批量路由安全检查",
    description:
      "把同一种检查并行应用到多个独立目标，再合并、去重和排序。适合批量文档分析、服务检查与目录级审查。",
    prompt:
      "Run a workflow to review every route in the bundled checkout-service sample for authentication or authorization risks. Summarize and deduplicate the most important issues, citing the affected route and line evidence.",
    topologyLabel: "fan out → collect → synthesize",
    topology: [["Route scope"], ["Review A", "Review B", "Review C", "Review D"], ["Deduplicate"], ["Top risks"]],
    completion: "全部发现的输入都被检查，结果完成合并与去重。",
  },
  {
    assistantId: "adversarial_verification",
    kind: "verify",
    family: "Confidence pattern",
    title: "Adversarial verification",
    short: "支付漏洞独立复核",
    description:
      "先产生候选结论，再要求独立角色逐条质疑与复核。适合误报成本高、可信度比速度更重要的审计任务。",
    prompt:
      "Run a workflow to audit the bundled payment module. Treat initial findings as unconfirmed and report only vulnerabilities that survive an independent skeptical review, with source evidence.",
    topologyLabel: "discover → challenge → confirm",
    topology: [["Payment module"], ["Candidate audit"], ["Independent checks"], ["Confirmed only"]],
    completion: "每个候选都有独立结论，最终只保留已确认问题。",
  },
  {
    assistantId: "generate_and_filter",
    kind: "filter",
    family: "Selection pattern",
    title: "Generate and filter",
    short: "订单数据模型设计",
    description:
      "让多个 subagents 独立形成候选，再根据明确需求筛选最强结果。适合需要扩大解空间、最终只保留优选结果的任务。",
    prompt:
      "Run a workflow to design an order data model for high-volume ordering, partial fulfillment, refunds, and immutable audit history. Produce several independent candidates, assess them against those requirements, and recommend the strongest result.",
    topologyLabel: "generate → score → keep best",
    topology: [["Design brief"], ["Proposal A", "Proposal B", "Proposal C"], ["Filter + rank"], ["Best"]],
    completion: "候选按同一组标准完成比较并选出一个推荐结果。",
  },
  {
    assistantId: "tournament",
    kind: "tournament",
    family: "Elimination pattern",
    title: "Tournament",
    short: "函数可读性重构赛",
    description:
      "多份候选两两比较，胜者持续晋级直到只剩一个。适合主观标准下的代码、文案或设计选择。",
    prompt: [
      "Run a workflow to produce five competing readability rewrites of this function,",
      "compare them head to head, and return the clearest result with the comparison reasons.",
      "",
      "```python",
      "def processOrder(order, inventory, gateway):",
      "    if order and order.get(\"status\") == \"new\":",
      "        if inventory.get(order[\"sku\"], 0) >= order[\"quantity\"]:",
      "            if gateway.charge(order[\"customer_id\"], order[\"total\"]):",
      "                inventory[order[\"sku\"]] -= order[\"quantity\"]",
      "                order[\"status\"] = \"paid\"",
      "                return True",
      "    return False",
      "```",
    ].join("\n"),
    topologyLabel: "5 → 3 → 2 → 1",
    topology: [["5 candidates"], ["3 winners"], ["2 finalists"], ["Champion"]],
    completion: "五个候选经过四次两两判断，淘汰路径产生唯一冠军。",
  },
  {
    assistantId: "loop_until_done",
    kind: "loop",
    family: "Convergence pattern",
    title: "Loop until done",
    short: "死代码穷举",
    description:
      "重复发现并对已有结果去重，直到某一轮没有新内容。适合范围未知、完成条件由结果收敛决定的任务。",
    prompt:
      "Run a workflow to find dead code in the bundled sample package. Continue checking while a pass adds new evidence, deduplicate the findings, and stop when another pass adds nothing.",
    topologyLabel: "discover → dedupe → converge",
    topology: [["Unknown scope"], ["Analyze"], ["New items?"], ["0 new · done"]],
    completion: "某一轮新增数为 0；若四轮仍未收敛则明确报告护栏停止。",
  },
];

export function PatternGlyph({ kind }: { kind: PatternKind }) {
  if (kind === "route") {
    return (
      <svg viewBox="0 0 60 40" aria-hidden="true">
        <circle cx="8" cy="20" r="4" /><path d="M12 20h10M22 20l10-12M22 20l10 12" />
        <rect x="33" y="3" width="18" height="10" /><rect x="33" y="15" width="18" height="10" />
        <rect x="33" y="27" width="18" height="10" />
      </svg>
    );
  }
  if (kind === "fan") {
    return (
      <svg viewBox="0 0 60 40" aria-hidden="true">
        <circle cx="8" cy="20" r="4" /><path d="M12 20h8M20 20l10-13M20 20h10M20 20l10 13" />
        <circle cx="35" cy="7" r="4" /><circle cx="35" cy="20" r="4" /><circle cx="35" cy="33" r="4" />
        <path d="M39 7l12 13M39 20h12M39 33l12-13" /><circle cx="54" cy="20" r="3" />
      </svg>
    );
  }
  if (kind === "verify") {
    return (
      <svg viewBox="0 0 60 40" aria-hidden="true">
        <circle cx="8" cy="20" r="4" /><path d="M12 20h9M31 20h7M47 20h6" />
        <rect x="21" y="14" width="10" height="12" /><circle cx="42" cy="20" r="5" />
        <path d="M39 20l2 2 4-5" />
      </svg>
    );
  }
  if (kind === "filter") {
    return (
      <svg viewBox="0 0 60 40" aria-hidden="true">
        <circle cx="8" cy="7" r="3" /><circle cx="8" cy="20" r="3" /><circle cx="8" cy="33" r="3" />
        <path d="M11 7h14M11 20h14M11 33h14M25 7l13 13M25 20h13M25 33l13-13M45 20h8" />
        <rect x="38" y="15" width="7" height="10" />
      </svg>
    );
  }
  if (kind === "tournament") {
    return (
      <svg viewBox="0 0 60 40" aria-hidden="true">
        <circle cx="6" cy="5" r="3" /><circle cx="6" cy="15" r="3" /><circle cx="6" cy="25" r="3" />
        <circle cx="6" cy="35" r="3" /><path d="M9 5h8v5h8M9 15h8v-5M9 25h8v5h8M9 35h8v-5M25 10h9v10h8M25 30h9V20M42 20h10" />
        <circle cx="55" cy="20" r="3" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 60 40" aria-hidden="true">
      <circle cx="9" cy="20" r="4" /><rect x="25" y="14" width="12" height="12" />
      <circle cx="52" cy="20" r="4" /><path d="M13 20h12M37 20h11M31 14V6H9v10M31 26v8h21V24" />
    </svg>
  );
}
{% endraw %}
