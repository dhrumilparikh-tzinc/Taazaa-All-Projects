# 🧪 POSTMAN API TESTING GUIDE - Step by Step

## Complete Guide to Test Medical RAG API Using Postman

Follow these exact steps to test the API:

---

## ✅ STEP 1: Install Postman

### Download
- Go to: https://www.postman.com/downloads/
- Download the version for your OS (Windows in your case)
- Install the application
- Open Postman

### First Time Setup
- Create a free account or skip
- You're ready to test!

---

## ✅ STEP 2: Import the API Collection

### Option A: Import Pre-Built Collection (RECOMMENDED)
1. In Postman, click **Import** button (top left)
2. Click **Upload Files**
3. Select: `Medical_RAG_API.postman_collection.json`
4. Click **Import**
5. You'll see all pre-configured requests!

### Option B: Manual Creation
1. Click **New** → **HTTP Request**
2. Name it "Test API Request"
3. Save to a collection

---

## ✅ STEP 3: Select HTTP Method

### For Your API:

#### Health Check (GET)
```
Method: GET
Purpose: Fetch data / Check API health
URL: http://localhost:8000/health
```

#### Ask Medical Question (POST)
```
Method: POST
Purpose: Create/Send data to API
URL: http://localhost:8000/ask
```

#### Ask Simple (POST)
```
Method: POST
Purpose: Create/Send data to API
URL: http://localhost:8000/ask/simple
```

---

## ✅ STEP 4: Enter API URL

### Health Check
```
http://localhost:8000/health
```

### Full Response Endpoint
```
http://localhost:8000/ask
```

### Simple Response Endpoint
```
http://localhost:8000/ask/simple
```

---

## ✅ STEP 5: Add Headers

### Headers Tab Setup

**For All Requests:**

| Header | Value |
|--------|-------|
| Content-Type | application/json |

**Steps in Postman:**
1. Click **Headers** tab
2. Click **Add** (or just type in the field)
3. Key: `Content-Type`
4. Value: `application/json`
5. Done! (It's already checked/enabled)

### Example Headers
```
Content-Type: application/json
```

---

## ✅ STEP 6: Add Request Body (for POST requests only)

### For `/ask` Endpoint:

**Steps in Postman:**
1. Click **Body** tab
2. Select **raw**
3. Make sure dropdown shows **JSON** (not Text)
4. Paste your JSON:

```json
{
  "question": "What are the symptoms of diabetes?",
  "k": 5
}
```

### For `/ask/simple` Endpoint:

```json
{
  "question": "What causes arthritis?",
  "k": 5
}
```

### For `/health` Endpoint:
- **No body needed** (it's a GET request)
- Leave Body empty

---

## ✅ STEP 7: Send Request

### To Send:
1. Click the **Send** button (blue button on right)
2. Wait for response (3-10 seconds)
3. See the response in the panel below

### Response Shows:
- **Status Code** (200, 400, 500, etc.)
- **Response Time** (how fast the API responded)
- **Response Body** (the answer as JSON)

---

## ✅ STEP 8: Understand Status Codes

### Status Codes Your API Returns:

| Code | Meaning | Your API |
|------|---------|----------|
| **200** | Success ✅ | `/health`, `/ask` work |
| **201** | Created | Not used in this API |
| **400** | Bad Request ❌ | Invalid input (e.g., question too long) |
| **401** | Unauthorized | Not needed (no auth) |
| **404** | Not Found ❌ | Wrong endpoint URL |
| **500** | Server Error ❌ | API crashed or API quota exceeded |

### What to Expect:

**200 OK** (Good!)
```json
{
  "status": "success",
  "question": "What are the symptoms of diabetes?",
  "answer": "Based on retrieved medical context...",
  "num_chunks": 5,
  "chunks": [...]
}
```

**400 Bad Request** (Invalid input)
```json
{
  "detail": [
    {
      "loc": ["body", "question"],
      "msg": "ensure this value has at least 1 characters",
      "type": "value_error"
    }
  ]
}
```

**500 Internal Server Error** (API issue)
```json
{
  "detail": "Failed to process question: [error details]"
}
```

---

## ✅ STEP 9: Test Different Scenarios

### Test 1️⃣: Valid Request (Should Work ✅)

**Endpoint:** `POST /ask`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "question": "What are the symptoms of diabetes?",
  "k": 5
}
```

**Expected Response:**
- Status: **200 OK** ✅
- Answer: Medical information about diabetes
- Chunks: 5 retrieved pieces of context

---

### Test 2️⃣: Missing Required Field (Should Fail ❌)

**Endpoint:** `POST /ask`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "k": 5
}
```

**Expected Response:**
- Status: **400 Bad Request** ❌
- Error: Missing required field "question"
- Message: `ensure this value has at least 1 characters`

---

### Test 3️⃣: Empty Question (Should Fail ❌)

**Endpoint:** `POST /ask`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "question": "",
  "k": 5
}
```

**Expected Response:**
- Status: **400 Bad Request** ❌
- Error: Question cannot be empty

---

### Test 4️⃣: Invalid Data Type (Should Fail ❌)

**Endpoint:** `POST /ask`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "question": "What is diabetes?",
  "k": "five"
}
```

**Expected Response:**
- Status: **400 Bad Request** ❌
- Error: k must be an integer, not a string

---

### Test 5️⃣: K Value Out of Range (Should Fail ❌)

**Endpoint:** `POST /ask`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "question": "What is diabetes?",
  "k": 100
}
```

**Expected Response:**
- Status: **400 Bad Request** ❌
- Error: ensure this value is less than or equal to 20

---

### Test 6️⃣: Wrong Endpoint (Should Fail ❌)

**Endpoint:** `POST /wrong-endpoint`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "question": "What is diabetes?",
  "k": 5
}
```

**Expected Response:**
- Status: **404 Not Found** ❌
- Error: The requested endpoint does not exist

---

### Test 7️⃣: Health Check (Should Always Work ✅)

**Endpoint:** `GET /health`

**Headers:**
```
Content-Type: application/json
```

**Body:**
- None (leave empty)

**Expected Response:**
- Status: **200 OK** ✅
- Response:
```json
{
  "status": "healthy",
  "message": "Medical RAG API is operational"
}
```

---

### Test 8️⃣: Simple Answer Endpoint (Should Work ✅)

**Endpoint:** `POST /ask/simple`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "question": "How to treat high blood pressure?",
  "k": 3
}
```

**Expected Response:**
- Status: **200 OK** ✅
- Response:
```json
{
  "question": "How to treat high blood pressure?",
  "answer": "Based on retrieved context, treatment options include..."
}
```

---

### Test 9️⃣: Very Long Question (Should Fail ❌)

**Endpoint:** `POST /ask`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "question": "What is diabetes and what are all the symptoms and causes and treatments and preventions and risk factors and complications and medications and alternative treatments and diet and exercise and lifestyle changes and genetic factors and environmental factors and immune system factors and hormonal factors and metabolic factors... (repeating more than 1000 characters)",
  "k": 5
}
```

**Expected Response:**
- Status: **400 Bad Request** ❌
- Error: ensure this value has at most 1000 characters

---

### Test 🔟: No API Key (If Authentication Added Later)

**Endpoint:** `GET /health`

**Expected Response:** (currently)
- Status: **200 OK** ✅
- No authentication required yet

---

## 🎯 Complete Test Checklist

### Before Testing
- [ ] Postman installed
- [ ] Medical_RAG_API.postman_collection.json imported
- [ ] API server is running (`python -m uvicorn api:app --host 0.0.0.0 --port 8000`)

### Valid Requests (Should Return 200 ✅)
- [ ] Test 1: Valid diabetes question
- [ ] Test 7: Health check
- [ ] Test 8: Simple answer request

### Invalid Requests (Should Return 400 ❌)
- [ ] Test 2: Missing question field
- [ ] Test 3: Empty question
- [ ] Test 4: Invalid data type (k as string)
- [ ] Test 5: k value too large (>20)
- [ ] Test 9: Question too long (>1000 chars)

### Error Scenarios (Should Return 404 or 500)
- [ ] Test 6: Wrong endpoint
- [ ] Test with Gemini quota exceeded (will show 500)

---

## 📊 Response Analysis

### Look at These in Postman:

**1. Status Code**
- Green = Success (2xx)
- Orange = Client error (4xx)
- Red = Server error (5xx)

**2. Response Time**
- First request: 5-10 seconds (models loading)
- Subsequent requests: 3-5 seconds
- If takes >30s: API might be stuck

**3. Response Body**
- Pretty-printed JSON
- Check the "answer" field
- Check "chunks" for retrieved context

**4. Response Headers**
- `Content-Type: application/json`
- Check CORS headers if calling from browser

---

## 🔧 Advanced Testing

### Save Test Results
1. Click **...** (three dots) next to request name
2. Select **Add test**
3. Create assertions:
```javascript
pm.test("Status code is 200", function () {
    pm.response.to.have.status(200);
});

pm.test("Response has answer", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.answer).to.exist;
});
```

### Create Test Suite
1. Create multiple requests in a collection
2. Click **Run** to run all tests
3. See results in Test Runner

### Save Requests
1. Each request is automatically saved
2. Switch between requests easily
3. Re-use for future testing

---

## 🎁 Pre-Configured Tests in Collection

The imported `Medical_RAG_API.postman_collection.json` includes:

```
✅ GET Health Status              (200 expected)
✅ GET Root Endpoint              (200 expected)
✅ POST Ask Medical Question      (200 expected)
✅ POST Ask Simple Question       (200 expected)
✅ POST COVID Question            (200 expected)
```

Just click and send! All headers and bodies are pre-filled.

---

## 🆘 Troubleshooting

### "Connection refused" Error
```
Issue: API not running
Solution: Start API with:
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

### "404 Not Found" Error
```
Issue: Wrong endpoint URL
Solution: Check URL is exactly:
http://localhost:8000/ask
(not /asks or /ask/ or /api/ask)
```

### "400 Bad Request" Error
```
Issue: Invalid request body
Solution: 
1. Check JSON is valid (use jsonlint.com)
2. Check required fields are present
3. Check data types match spec
```

### "500 Server Error" Error
```
Issue: API crashed or quota exceeded
Solution:
1. Check API console for errors
2. Check Gemini API quota
3. Restart API server
```

### "No response" After 30 seconds
```
Issue: API taking too long or frozen
Solution:
1. Click Cancel
2. Check API logs
3. Restart API
4. Try a simpler question first
```

---

## 📝 Testing Template (Use This)

**Request Name:**
- [ ] Test Name Here

**Endpoint:**
- [ ] HTTP Method: GET/POST
- [ ] URL: http://localhost:8000/...

**Headers:**
- [ ] Content-Type: application/json

**Body:**
```json
{
  "field": "value"
}
```

**Expected Status:**
- [ ] 200 / 400 / 500 (circle one)

**Expected Response:**
- [ ] Contains "answer"
- [ ] Contains "status"
- [ ] Other assertions...

**Result:**
- [ ] PASS ✅
- [ ] FAIL ❌

---

## ✅ Final Checklist

Before you say "API is tested":

- [x] Installed Postman
- [x] Imported collection
- [x] API is running
- [x] Health check works
- [x] Valid request works
- [x] Invalid requests fail appropriately
- [x] All 10 test scenarios passed
- [x] Status codes are correct
- [x] Response format is correct
- [x] No errors in API console

---

## 🎉 You're Done Testing!

Your API is fully tested and ready to share with Postman!

**Next Steps:**
1. Share the Postman collection
2. Share this guide
3. Others can test immediately
4. No API issues! ✅

---

**Everything is testable and working! 🚀**
