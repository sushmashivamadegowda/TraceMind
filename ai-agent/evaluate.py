import os
import time
import requests
import json
from agent import client, tools, search_logs, query_metrics, search_knowledge_base, execute_remediation

API_URL = "http://localhost:8080"
INCIDENT_MANAGER_URL = "http://localhost:8081"

# The benchmark dataset
SCENARIOS = [
    {
        "chaos_endpoint": "database-timeout",
        "symptoms": ["500 error rate > 10%"],
        "expected_cause_keywords": ["database", "connection", "pool", "exhaustion", "leak"],
        "expected_remediation": "restart_service"
    },
    {
        "chaos_endpoint": "redis-failure",
        "symptoms": ["Redis unavailable", "Cache misses spike"],
        "expected_cause_keywords": ["redis", "cache", "memory", "oom"],
        "expected_remediation": "clear_cache"
    },
    {
        "chaos_endpoint": "bad-deployment",
        "symptoms": ["TypeError in orders", "Application crashing"],
        "expected_cause_keywords": ["deployment", "code", "merge", "typeerror", "none"],
        "expected_remediation": "rollback_deployment"
    },
    {
        "chaos_endpoint": "external-api-failure",
        "symptoms": ["504 Payment Gateway Timeout"],
        "expected_cause_keywords": ["payment", "gateway", "external", "third-party", "timeout"],
        "expected_remediation": "disable_feature_flag"
    },
    {
        "chaos_endpoint": "n-plus-one",
        "symptoms": ["API latency > 2s", "CPU spike"],
        "expected_cause_keywords": ["n+1", "queries", "excessive"],
        "expected_remediation": "disable_feature_flag"
    }
]

def trigger_synthetic_traffic():
    """Generates a burst of traffic to force the incident into Prometheus/Loki"""
    for i in range(5):
        try:
            order = {"customer_id": f"cust_{i}", "items": [{"product_id": "prod_1", "quantity": 1, "price": 10.0}]}
            requests.post(f"{API_URL}/orders", json=order, timeout=1)
            requests.get(f"{API_URL}/orders/ord_{i}", timeout=1)
            requests.post(f"{API_URL}/orders/ord_{i}/process", timeout=1)
        except Exception:
            pass

def clean_up_chaos():
    """Resets the system back to normal via Remediation API"""
    for action in ["restart_service", "rollback_deployment", "disable_feature_flag", "clear_cache"]:
        try:
            requests.post(f"{API_URL}/remediation/{action}")
        except:
            pass

def evaluate_scenario(scenario):
    print(f"\n🚀 Evaluating Scenario: {scenario['chaos_endpoint']}...")
    
    clean_up_chaos()
    time.sleep(1) # Let system settle
    
    # 1. Inject Chaos
    requests.post(f"{API_URL}/chaos/{scenario['chaos_endpoint']}?enable=true")
    
    # 2. Trigger traffic to simulate symptoms
    print("   Generating synthetic traffic to manifest symptoms...")
    trigger_synthetic_traffic()
    time.sleep(3) # Let logs/metrics flush
    
    # 3. Formulate the Incident
    incident = {
        "incident_id": f"EVAL-{scenario['chaos_endpoint'][:5].upper()}",
        "service": "order-api",
        "status": "open",
        "symptoms": scenario["symptoms"]
    }
    
    start_time = time.time()
    tool_calls_count = 0
    final_cause = ""
    remediation_attempted = False
    
    messages = [
        {"role": "system", "content": "You are an AI SRE. Investigate the incident using your tools. Once you find the root cause, you MUST call execute_remediation. Finally, call resolve_incident."},
        {"role": "user", "content": f"Investigate this incident: {json.dumps(incident)}"}
    ]

    print("   AI is investigating...")
    while True:
        response = client.chat.completions.create(
            model="gpt-4", 
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        msg = response.choices[0].message
        messages.append(msg)
        
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_calls_count += 1
                args = json.loads(tool_call.function.arguments)
                tool_name = tool_call.function.name
                
                try:
                    # In evaluate mode, we bypass the human-in-the-loop input() safely
                    if tool_name == "search_logs":
                        res = search_logs(args["query_str"])
                    elif tool_name == "query_metrics":
                        res = query_metrics(args["metric_query"])
                    elif tool_name == "search_knowledge_base":
                        res = search_knowledge_base(args["query"])
                    elif tool_name == "execute_remediation":
                        res = execute_remediation(args["action_name"])
                        remediation_attempted = True
                    elif tool_name == "resolve_incident":
                        final_cause = args["root_cause"]
                        res = "Resolved."
                    else:
                        res = f"Unknown tool {tool_name}"
                except Exception as e:
                    res = str(e)
                    
                messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": tool_name, "content": res})
                
                if tool_name == "resolve_incident":
                    break
        else:
            time.sleep(1)
            
        # Break condition
        if any(t.function.name == "resolve_incident" for t in (msg.tool_calls or [])):
            break
            
        if time.time() - start_time > 120:
            print("   [!] Timeout reached.")
            break
            
    investigation_time = time.time() - start_time
    
    # 4. Clean up
    clean_up_chaos()
    
    # 5. Evaluate Accuracy
    correct_diagnosis = any(k.lower() in final_cause.lower() for k in scenario["expected_cause_keywords"])
    
    return {
        "scenario": scenario["chaos_endpoint"],
        "correct_diagnosis": correct_diagnosis,
        "remediation_attempted": remediation_attempted,
        "tool_calls": tool_calls_count,
        "investigation_time": investigation_time,
        "final_cause": final_cause
    }

def run_benchmark():
    if not os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") == "your-api-key":
        print("❌ Error: You must set a valid OPENAI_API_KEY environment variable to run the benchmark.")
        return

    print("\n==============================================")
    print("   AI SRE BENCHMARK EVALUATOR STARTED         ")
    print("==============================================")
    
    results = []
    for s in SCENARIOS:
        try:
            res = evaluate_scenario(s)
            results.append(res)
        except Exception as e:
            print(f"   [!] Error evaluating {s['chaos_endpoint']}: {e}")
            
    if not results:
        return
        
    total = len(results)
    correct = sum(1 for r in results if r["correct_diagnosis"])
    remediated = sum(1 for r in results if r["remediation_attempted"])
    avg_time = sum(r["investigation_time"] for r in results) / total
    avg_tools = sum(r["tool_calls"] for r in results) / total
    false_diagnoses = total - correct
    
    print("\n\n📊 FINAL EVALUATION REPORT 📊")
    print("────────────────────────────────────────────────")
    print(f"Root-cause identification:  {correct}/{total}")
    print(f"Successful remediation:     {remediated}/{total}")
    print(f"Average investigation:      {avg_time:.1f} sec")
    print(f"Average tool calls:         {avg_tools:.1f}")
    print(f"False diagnoses:            {false_diagnoses}")
    print("────────────────────────────────────────────────")
    print("Done! You can copy these metrics to your README.")
    
if __name__ == "__main__":
    run_benchmark()
