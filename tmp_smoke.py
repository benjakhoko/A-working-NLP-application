from backend import create_app
from backend.extensions import db
app = create_app("testing")
with app.app_context():
    db.create_all()
c = app.test_client()
r = c.post("/api/auth/register", json={"full_name":"Test User","email":"test@example.com","password":"Password123","confirm_password":"Password123"})
print("register", r.status_code, r.get_json())
text = "Artificial intelligence is transforming modern healthcare. Machine learning models can detect diseases from medical images with high accuracy. However, clinicians remain concerned about data privacy and model interpretability. Researchers are developing explainable systems that help doctors trust automated recommendations. The technology is promising but requires careful validation before widespread adoption."
r = c.post("/api/keywords/extract", json={"text":text,"algorithm":"tfidf","top_n":8})
print("keywords", r.status_code, [k["keyword"] for k in r.get_json()["data"]["result"]["keywords"]])
r = c.post("/api/keywords/extract", json={"text":text,"algorithm":"compare","top_n":5})
print("compare", r.status_code, list(r.get_json()["data"]["result"]["algorithms"]))
r = c.post("/api/summarization/extractive", json={"text":text,"length":"short"})
print("extractive", r.status_code, r.get_json()["data"]["result"]["summary"][:120])
r = c.post("/api/language/detect", json={"text":text})
print("language", r.status_code, r.get_json()["data"]["result"]["name"])
r = c.post("/api/sentiment/analyze", json={"text":text})
print("sentiment", r.status_code, r.get_json()["data"]["result"]["label"], r.get_json()["data"]["result"]["compound_score"])
r = c.get("/api/dashboard/statistics")
print("stats", r.status_code, r.get_json()["data"]["totals"])
r = c.get("/api/history")
print("history", r.status_code, r.get_json()["data"]["pagination"]["total"])
aid = c.get("/api/history").get_json()["data"]["analyses"][0]["id"]
r = c.post("/api/reports/generate", json={"analysis_id":aid})
print("report", r.status_code, r.headers.get("content-type"), len(r.data))
for path in ["/login","/register","/dashboard","/workspace","/documents","/history","/profile","/analysis/"+str(aid)]:
    rr = c.get(path)
    print(path, rr.status_code, len(rr.data))
