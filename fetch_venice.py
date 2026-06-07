import httpx
import json

def fetch_venice_models():
    api_key = "VENICE_INFERENCE_KEY_5ToKzyzApAPNLrhf1jFgfqTikWjzdXDDQ-cL9ExmwY"
    resp = httpx.get(
        "https://api.venice.ai/api/v1/models", 
        headers={"Authorization": f"Bearer {api_key}"}
    )
    if resp.status_code != 200:
        print(f"Error fetching: {resp.text}")
        return
        
    data = resp.json()
    models = []
    
    # We also keep the gemini aliases around for legacy compatibility if we want, 
    # but the venice/* wildcard handles them nicely.
    for m in data.get('data', []):
        if m.get('type') != 'text':
            # Optionally filter non-text models, but let's include all to be safe 
            # (or just assume they are all fine). Venice returns a list of models.
            pass
            
        m_id = m['id']
        mod = {
            "id": f"venice/{m_id}",
            "label": m_id,
            "provider": "Venice",
            "tier": "high" if "minimax" in m_id.lower() or "llama-3.3" in m_id.lower() else "mid",
            "context_length": 128000,
            "pricing": {"prompt": 0, "completion": 0},
            "modality": "text+image+file->text",
            "description": f"Venice model: {m_id}. Powered by Venice."
        }
        
        # Set defaults based on user preference
        if "minimax-m3" in m_id.lower():
            mod["default"] = True
            mod["description"] = "Venice model: minimax-m3 for the hard stuff."
        if "qwen3.5-9b" in m_id.lower() or "qwen" in m_id.lower():
            if "qwen3.5-9b" in m_id.lower() or "qwen2.5-coder" in m_id.lower():
                mod["expertDefault"] = True
                mod["description"] = "Venice model: qwen for the fast stuff."
                
        models.append(mod)

    # Make sure at least one default and one expertDefault exists
    if not any(m.get('default') for m in models) and models:
        models[0]['default'] = True
    if not any(m.get('expertDefault') for m in models) and len(models) > 1:
        models[1]['expertDefault'] = True

    with open("c:/Users/vivga/OneDrive/AI/AI Projects/K-dense/web/src/data/models.json", "w", encoding="utf-8") as f:
        json.dump(models, f, indent=2)
    print(f"Wrote {len(models)} Venice models to models.json")

if __name__ == "__main__":
    fetch_venice_models()
