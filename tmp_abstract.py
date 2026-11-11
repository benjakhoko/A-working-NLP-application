from backend import create_app
from backend.extensions import db
app = create_app("testing")
with app.app_context(): db.create_all()
c = app.test_client()
c.post("/api/auth/register", json={"full_name":"Model Tester","email":"models@example.com","password":"Password123"})
text = ("Artificial intelligence is transforming modern healthcare. Machine learning models can detect diseases from medical images with high accuracy. "
"However, clinicians remain concerned about data privacy and model interpretability. Researchers are developing explainable systems that help doctors trust automated recommendations. "
"The technology is promising but requires careful validation before widespread adoption. Hospitals are testing these systems in controlled trials, and regulators are drafting new rules for clinical AI. "
"Patients want to understand how decisions are made, while doctors need tools that fit their existing workflows. The next decade will determine whether AI becomes a trusted assistant or another source of risk.")
import time
t=time.time(); r=c.post("/api/summarization/abstractive", json={"text":text,"length":"short"}); print("abstractive", r.status_code, "elapsed", round(time.time()-t,1)); print(r.get_json())
