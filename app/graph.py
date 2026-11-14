"""LangGraph agents: supervisor -> retrieval / routing / onboarding, HITL gate.

One graph for /ask, one small graph for the onboarding checklist. Nodes are
pure state-in/state-out except the audit writer and case store, which are
injected through the Copilot instance.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from langgraph.graph import END, StateGraph

from . import config
from .cases import AuditLog, CaseStore
from .ingest import Clause, PolicyDoc, all_clauses, load_policies
from .llm import AzureError, get_answerer
from .metrics import Metrics
from .pii import mask_pii
from .retrieval import ScoredClause, get_retriever


class GraphState(TypedDict, total=False):
    request_id: str
    question: str
    employee_id: str | None
    role: str
    location: str
    start_date: str | None
    retrieved: list[dict]
    scored: list[ScoredClause]
    top_score: float
    route: str  # answered | routed_to_hr
    route_reason: str | None
    draft_reply: str
    answer: str | None
    citations: list[dict]
    confidence: float
    case_id: str | None
    checklist: list[dict]


def _citation(scored) -> dict:
    clause: Clause = scored.clause
    return {
        "doc_id": clause.doc_id,
        "clause_id": clause.clause_id,
        "title": clause.title,
        "quote": clause.text,
    }


def _draft_reply(question: str, route_reason: str, citations: list[dict]) -> str:
    cite = ""
    if citations:
        first = citations[0]
        cite = (
            f" The policy clause that may apply is {first['title']} "
            f"({first['doc_id']}, clause {first['clause_id']})."
        )
    return (
        f"Dear colleague,\n\nThank you for your question: "
        f"\"{mask_pii(question)}\". This has been routed to HR because it "
        f"needs a human decision ({route_reason}).{cite} "
        "HR will respond within 5 working days.\n\n— HR team"
    )


class Copilot:
    def __init__(self, docs: list[PolicyDoc] | None = None,
                 audit_path=None, answerer=None) -> None:
        self.docs = docs if docs is not None else load_policies()
        self.clauses = all_clauses(self.docs)
        self.retriever = get_retriever(self.clauses)
        self.answerer = answerer if answerer is not None else get_answerer()
        self.cases = CaseStore()
        self.audit = AuditLog(path=audit_path)
        self.metrics = Metrics()
        self._ask_graph = self._build_ask_graph()
        self._onboarding_graph = self._build_onboarding_graph()

    # -- ask graph -----------------------------------------------------
    def _build_ask_graph(self):
        def supervisor(state: GraphState) -> GraphState:
            reason = config.classify_sensitive(state["question"])
            if reason:
                return {**state, "route": "routed_to_hr", "route_reason": reason}
            return {**state, "route_reason": None}

        def retrieval(state: GraphState) -> GraphState:
            # Runs for sensitive questions too: the routing agent needs the
            # retrieved clauses as case citations (SPEC section 5.4).
            scored = self.retriever.retrieve(state["question"], k=config.RETRIEVAL_K)
            citations = [_citation(s) for s in scored]
            top = scored[0].score if scored else 0.0
            update: GraphState = {**state, "retrieved": citations, "scored": scored,
                                  "top_score": top}
            if state.get("route") != "routed_to_hr" and top < config.RETRIEVAL_FLOOR:
                update["route"] = "routed_to_hr"
                update["route_reason"] = "low_confidence"
            return update

        def answer(state: GraphState) -> GraphState:
            # Reuses the retrieval node's results; never re-runs retrieval.
            scored = state.get("scored", [])
            text, confidence = self.answerer.answer(state["question"], scored)
            return {**state, "answer": text, "citations": state.get("retrieved", []),
                    "confidence": confidence, "route": "answered", "case_id": None}

        def routing(state: GraphState) -> GraphState:
            citations = state.get("retrieved", [])
            draft = _draft_reply(state["question"], state["route_reason"] or "sensitive", citations)
            case = self.cases.create(state["question"], state["route_reason"] or "sensitive",
                                     draft, citations)
            self.audit.append("case_created", state.get("request_id", ""),
                              {"case_id": case.id, "route_reason": case.route_reason,
                               "doc_ids": [c["doc_id"] for c in citations]})
            return {**state, "draft_reply": draft, "case_id": case.id,
                    "answer": None, "citations": [], "confidence": 0.0}

        def after_retrieval(state: GraphState) -> str:
            return "routing" if state.get("route") == "routed_to_hr" else "answer"

        graph = StateGraph(GraphState)
        graph.add_node("supervisor", supervisor)
        graph.add_node("retrieval", retrieval)
        graph.add_node("answer", answer)
        graph.add_node("routing", routing)
        graph.set_entry_point("supervisor")
        # Retrieval runs for every question: answerable ones need it to
        # answer, sensitive ones need it for the case citations.
        graph.add_edge("supervisor", "retrieval")
        graph.add_conditional_edges("retrieval", after_retrieval,
                                    {"routing": "routing", "answer": "answer"})
        graph.add_edge("answer", END)
        graph.add_edge("routing", END)
        return graph.compile()

    # -- onboarding graph ----------------------------------------------
    def _build_onboarding_graph(self):
        def onboarding(state: GraphState) -> GraphState:
            return {**state, "checklist": self._build_checklist(state["role"], state["location"])}

        graph = StateGraph(GraphState)
        graph.add_node("onboarding", onboarding)
        graph.set_entry_point("onboarding")
        graph.add_edge("onboarding", END)
        return graph.compile()

    def _build_checklist(self, role: str, location: str) -> list[dict]:
        def item(day: int, title: str, detail: str, owner: str,
                 doc_id: str, clause_id: str) -> dict:
            clause = next((c for c in self.clauses if c.clause_id == clause_id), None)
            return {"day": day, "title": title, "detail": detail, "owner": owner,
                    "source": {"doc_id": doc_id, "clause_id": clause_id,
                               "title": clause.title if clause else doc_id,
                               "quote": clause.text if clause else ""}}

        role_l, loc_l = role.lower(), location.lower()
        is_remote = "remote" in loc_l
        if is_remote:
            laptop = item(1, "Receive your laptop and logins",
                          "Your laptop is shipped to your home address before your joining date. "
                          "Change your password at first login and enable multi-factor authentication.",
                          "IT", "ONB-IT", "ONB-IT-01")
        else:
            laptop = item(1, "Collect laptop and logins",
                          "Collect your laptop from IT and change your password at first login; enable multi-factor authentication.",
                          "IT", "ONB-IT", "ONB-IT-01")
        items = [
            item(1, "Complete HR paperwork",
                 "Submit identity proof, address proof, bank details and tax declarations to HR.",
                 "HR", "ONB", "ONB-01"),
            laptop,
            item(2, "Meet your buddy",
                 "Your assigned buddy introduces you to the team and answers day-to-day questions.",
                 "Buddy", "ONB", "ONB-02"),
            item(3, "Complete compliance training",
                 "Finish the code of conduct, data privacy and information security training.",
                 "Employee", "ONB", "ONB-03"),
            item(4, "Start first project work",
                 "Begin your first project task with your manager and confirm the week-1 goals.",
                 "Manager", "ONB", "ONB-04"),
            item(5, "Probation plan review",
                 "Agree the probation plan and the month-3 review date with your manager.",
                 "Manager", "ONB", "ONB-05"),
        ]
        # Manager first: "Engineering Manager" contains "engineer", so the
        # manager check must come before the engineer check.
        if "manager" in role_l or "lead" in role_l:
            items.insert(2, item(2, "Meet your team and review goals",
                                 "Hold a first team meeting to introduce yourself and review the team's current goals.",
                                 "Manager", "ONB", "ONB-04"))
        elif any(w in role_l for w in ("engineer", "developer", "data", "designer", "analyst")):
            items.insert(2, item(2, "Set up your development environment",
                                 "Get role-specific software and project access from IT through the service desk.",
                                 "IT", "ONB-IT", "ONB-IT-03"))
        if is_remote:
            items.insert(1, item(1, "Set up your remote workspace",
                                 "Confirm your home-office setup and test your laptop, monitor and headset with IT.",
                                 "Employee", "ONB-IT", "ONB-IT-01"))
        else:
            items.insert(1, item(1, "Collect office badge and desk",
                                 "Collect your office badge from HR and confirm your desk and team seating.",
                                 "HR", "ONB", "ONB-01"))
        return items[:8]

    # -- public API ------------------------------------------------------
    def ask(self, question: str, employee_id: str | None = None) -> dict:
        request_id = "req_" + uuid.uuid4().hex[:12]
        self.audit.append("question_received", request_id,
                          {"employee_id": employee_id or "",
                           "question": mask_pii(question)})
        state = self._ask_graph.invoke(
            {"question": mask_pii(question), "employee_id": employee_id,
             "request_id": request_id})
        if state["route"] == "answered":
            self.metrics.record_answered(state["confidence"], bool(state["citations"]))
            self.audit.append("answered", request_id,
                              {"route": "answered", "confidence": state["confidence"],
                               "doc_ids": [c["doc_id"] for c in state["citations"]]})
        else:
            self.metrics.record_routed()
            self.audit.append("routed", request_id,
                              {"route": "routed_to_hr", "route_reason": state["route_reason"],
                               "case_id": state.get("case_id")})
        return {
            "request_id": request_id,
            "route": state["route"],
            "route_reason": state.get("route_reason"),
            "answer": state.get("answer"),
            "citations": state.get("citations", []),
            "confidence": state.get("confidence", 0.0),
            "case_id": state.get("case_id"),
            "message": ("This question has been routed to HR with a draft reply. "
                        "An HR reviewer will respond.") if state["route"] == "routed_to_hr" else None,
        }

    def checklist(self, employee_id: str, role: str, location: str,
                  start_date: str | None = None) -> dict:
        state = self._onboarding_graph.invoke(
            {"role": role, "location": location, "start_date": start_date})
        return {"employee_id": employee_id, "role": role, "location": location,
                "checklist": state["checklist"]}

    def review_case(self, case_id: str, decision: str, reviewer: str,
                    note: str | None) -> dict | None:
        case = self.cases.review(case_id, decision, reviewer, note)
        if case is None:
            return None
        self.audit.append("case_reviewed", "req_" + uuid.uuid4().hex[:12],
                          {"case_id": case.id, "decision": decision, "reviewer": reviewer})
        return {
            "id": case.id, "status": case.status, "question": case.question,
            "route_reason": case.route_reason, "draft_reply": case.draft_reply,
            "citations": case.citations, "created_at": case.created_at,
            "reviewed_by": case.reviewed_by, "review_note": case.review_note,
            "reviewed_at": case.reviewed_at,
        }
