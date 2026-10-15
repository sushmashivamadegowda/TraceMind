import os
import json
import time
import requests
from openai import OpenAI
import chroma_rag

INCIDENT_MANAGER_URL = "http://localhost:8081"
PROMETHEUS_URL = "http://localhost:9090"
LOKI_URL = "http://localhost:3100"
API_URL = "http://localhost:8080"

# Uses standard OPENAI_API_KEY environment variable
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))

# ==========================================
# Phase 10: AI Safety & Risk Governance
# ==========================================
ACTION_RISK_TIERS = {
    "search_logs": "LOW_RISK",             # Safe: Read-only
    "query_metrics": "LOW_RISK",           # Safe: Read-only
    "search_knowledge_base": "LOW_RISK",   # Safe: Read-only
    "resolve_incident": "LOW_RISK",        # Safe: Updates the ticket state
    "execute_remediation": "HIGH_RISK"     # Dangerous: Modifies production state
}

FORBIDDEN_ACTIONS = ["delete_data", "drop_database", "flush_all"]

def request_human_approval(tool_name, args):
    print(f"\n⚠️  [SAFETY GATE] HIGH RISK ACTION DETECTED ⚠️")
    print(f"Tool requested: {tool_name}")
    print(f"Payload: {json.dumps(args, indent=2)}")
    
    # Hard safety guardrails - NEVER automatically allow destructive actions
    action = args.get('action_name')
    if tool_name == "execute_remediation" and (not action or action in FORBIDDEN_ACTIONS):
        print(f"❌ [POLICY ENFORCER]: AUTOMATIC REJECT. '{action}' violates core safety policies.")
        return False, f"ERROR: Core policy violation. Action '{action}' is strictly forbidden for AI."

    approval = input(f"\n✋ Human Operator, do you approve this execution? (y/n): ")
    if approval.lower() == 'y':
        return True, "Human approved"
    else:
        return False, "Human rejected"

# ==========================================
# Tool Implementations
# ==========================================

def search_logs(query_str):
    print(f"[*] Tool Executing [LOW RISK]: search_logs -> {query_str}")
    r = requests.get(f"{LOKI_URL}/loki/api/v1/query", params={"query": query_str}, timeout=10)
    r.raise_for_status()
    return json.dumps(r.json())

def query_metrics(metric_query):
    print(f"[*] Tool Executing [LOW RISK]: query_metrics -> {metric_query}")
    r = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": metric_query}, timeout=10)
    r.raise_for_status()
    return json.dumps(r.json())

def search_knowledge_base(query):
    print(f"[*] Tool Executing [LOW RISK]: search_knowledge_base -> {query}")
    docs = chroma_rag.search_kb(query, limit=2)
    return json.dumps(docs)

def execute_remediation(action_name):
    print(f"[*] Tool Executing [HIGH RISK]: execute_remediation -> {action_name}")
    try:
        r = requests.post(f"{API_URL}/remediation/{action_name}", timeout=10)
        r.raise_for_status()
        return json.dumps(r.json())
    except Exception as e:
        return str(e)

def resolve_incident(incident_id, root_cause, confidence):
    print(f"[*] Tool Executing [LOW RISK]: resolve_incident -> {root_cause} (Confidence: {confidence})")
    r = requests.patch(
        f"{INCIDENT_MANAGER_URL}/incidents/{incident_id}",
        json={"root_cause": root_cause, "confidence": confidence, "status": "resolved"},
        timeout=10
    )
    r.raise_for_status()
    return json.dumps(r.json())

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_logs",
            "description": "Query Loki for logs.",
            "parameters": {"type": "object", "properties": {"query_str": {"type": "string"}}, "required": ["query_str"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_metrics",
            "description": "Query Prometheus for metrics.",
            "parameters": {"type": "object", "properties": {"metric_query": {"type": "string"}}, "required": ["metric_query"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Query the RAG vector database for runbooks.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_remediation",
            "description": "Execute a remediation action to fix the system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_name": {"type": "string", "enum": ["restart_service", "rollback_deployment", "clear_cache", "disable_feature_flag", "delete_data"]}
                },
                "required": ["action_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_incident",
            "description": "Provide the final root cause to resolve the incident.",
            "parameters": {
                "type": "object",
                "properties": {
                    "incident_id": {"type": "string"},
                    "root_cause": {"type": "string"},
                    "confidence": {"type": "number"}
                },
                "required": ["incident_id", "root_cause", "confidence"]
            }
        }
    }
]

def investigate_incident(incident):
    print(f"\n=============================================")
    print(f"🚨 STARTING INVESTIGATION: {incident['incident_id']}")
    print(f"Symptoms: {incident['symptoms']}")
    print(f"=============================================\n")

    messages = [
        {"role": "system", "content": "You are an autonomous AI SRE. Investigate the incident using logs, metrics, and knowledge base. If you need to mutate production state, use execute_remediation. The system will handle governance. Finally, resolve the incident."},
        {"role": "user", "content": f"Investigate this incident: {json.dumps(incident)}"}
    ]

    while True:
        response = client.chat.completions.create(
            model="gpt-4", 
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=600  # Restrict LLM verbosity to save tokens
        )
        
        response_message = response.choices[0].message
        
        if response_message.content:
            print(f"🧠 Agent Reasoning:\n{response_message.content}\n")
            
        messages.append(response_message)
        
        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                tool_name = tool_call.function.name
                
                try:
                    # 1. Governance check
                    tier = ACTION_RISK_TIERS.get(tool_name, "HIGH_RISK")
                    
                    if tier == "HIGH_RISK":
                        approved, msg = request_human_approval(tool_name, args)
                        if not approved:
                            # Re-inject the rejection back into the LLM context so it can pivot
                            res = msg 
                            print(f"[*] Skipping execution due to rejection.")
                        else:
                            # Approved, proceed with actual execution
                            if tool_name == "execute_remediation":
                                res = execute_remediation(args["action_name"])
                    else:
                        # LOW_RISK, proceed automatically
                        if tool_name == "search_logs":
                            res = search_logs(args["query_str"])
                        elif tool_name == "query_metrics":
                            res = query_metrics(args["metric_query"])
                        elif tool_name == "search_knowledge_base":
                            res = search_knowledge_base(args["query"])
                        elif tool_name == "resolve_incident":
                            res = resolve_incident(args["incident_id"], args["root_cause"], args["confidence"])
                        else:
                            res = f"Unknown function {tool_name}"
                            
                except Exception as e:
                    res = f"Error executing tool: {str(e)}"
                    
                # Aggressively truncate tool outputs to prevent context explosion
                res_str = str(res)
                if len(res_str) > 1500:
                    res_str = res_str[:1500] + "\n... [TRUNCATED TO SAVE TOKENS]"
                    
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": tool_call.function.name,
                    "content": res_str
                })
                
                if tool_name == "resolve_incident":
                    print("\n✅ INCIDENT RESOLVED!")
                    return
        else:
            print(f"🧠 Agent stopped making tool calls. Final output:\n{response_message.content}")
            break
            
        time.sleep(2)

def run():
    print("[*] Initializing RAG Knowledge Base...")
    chroma_rag.init_knowledge_base()

    try:
        r = requests.get(f"{INCIDENT_MANAGER_URL}/incidents")
        r.raise_for_status()
    except Exception as e:
        print(f"Could not reach Incident Manager: {e}")
        return
        
    incidents = [i for i in r.json() if i["status"] in ["open", "pending_approval"]]
    
    if not incidents:
        print("No open incidents to investigate at this time.")
        return
    
    for inc in incidents:
        investigate_incident(inc)

if __name__ == "__main__":
    run()
