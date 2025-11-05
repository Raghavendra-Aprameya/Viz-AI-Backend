# Business Insights Endpoints - Quick Reference

## 🎯 Two Endpoints Available

### **1. Single Database Insights** (Fast & Focused)
```
POST /api/v1/backend/business-insights
```

### **2. Project-Wide Insights** (Comprehensive & Strategic)  
```
POST /api/v1/backend/projects/{project_id}/business-insights
```

---

## 📊 Endpoint Comparison

| Feature | Single Database | Project-Wide |
|---------|----------------|--------------|
| **URL** | `/business-insights` | `/projects/{id}/business-insights` |
| **Scope** | One database | All databases in project |
| **Request Body** | `{ "database_connection_id": "uuid" }` | None (project_id in URL) |
| **LLM Calls** | 2 | 2N + 1 (N = # of databases) |
| **Execution Time** | 12-35 seconds | 30-120 seconds |
| **Output** | Single database analysis | All DBs + consolidated strategy |
| **Best For** | Quick checks, monitoring | Executive reports, strategy |

---

## 🚀 Usage Examples

### **Single Database Insights**

**Request:**
```bash
POST /api/v1/backend/business-insights
Content-Type: application/json
Authorization: Bearer {JWT_TOKEN}

{
  "database_connection_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "message": "Business insights generated successfully",
  "database_name": "Sales Database",
  "database_type": "postgres",
  "kpis_analyzed": 10,
  "kpi_queries": [...],
  "query_results": [...],
  "insights": {
    "executive_summary": "...",
    "key_metrics": [...],
    "recommendations": [...],
    "areas_of_concern": [...]
  }
}
```

---

### **Project-Wide Insights**

**Request:**
```bash
POST /api/v1/backend/projects/2f96eace-5738-4c9f-afba-155203ee1434/business-insights
Content-Type: application/json
Authorization: Bearer {JWT_TOKEN}

# No body required (or send empty: {})
```

**Response:**
```json
{
  "message": "Project-wide business insights generated successfully",
  "project_id": "2f96eace-5738-4c9f-afba-155203ee1434",
  "project_name": "E-Commerce Analytics",
  "total_databases_analyzed": 3,
  "successful_analyses": 3,
  
  "database_insights": [
    {
      "database_id": "db-uuid-1",
      "database_name": "Sales Database",
      "status": "success",
      "kpis_analyzed": 10,
      "successful_queries": 10,
      "insights": { /* Full insights */ }
    },
    {
      "database_id": "db-uuid-2",
      "database_name": "Customer Database",
      "status": "success",
      "kpis_analyzed": 10,
      "successful_queries": 9,
      "insights": { /* Full insights */ }
    },
    {
      "database_id": "db-uuid-3",
      "database_name": "Inventory Database",
      "status": "success",
      "kpis_analyzed": 10,
      "successful_queries": 10,
      "insights": { /* Full insights */ }
    }
  ],
  
  "consolidated_insights": {
    "overall_health_score": "good",
    "health_assessment": "Strong revenue growth with retention opportunities...",
    "cross_database_patterns": [
      "Revenue correlates with customer acquisition rate",
      "Inventory turnover lags sales velocity"
    ],
    "strategic_priorities": [
      {
        "rank": 1,
        "title": "Optimize Inventory Management",
        "description": "Align inventory with sales velocity...",
        "impact": "high"
      }
      // ... 4 more priorities
    ],
    "risk_assessment": {
      "critical_risks": ["Overstocking in Electronics ($250K risk)"],
      "moderate_risks": ["Supplier concentration vulnerability"]
    },
    "opportunities": [
      {
        "title": "Geographic Expansion - Western Region",
        "description": "12% penetration, 35% demographic...",
        "potential_impact": "Increase revenue by 24%"
      }
    ]
  }
}
```

---

## 🔑 Configuration Required

Add to your `.env` file:
```bash
GEMINI_API_KEY=your-gemini-api-key-here
```

Get your API key from: https://makersuite.google.com/app/apikey

---

## 📝 When to Use Each

### Use **Single Database** (`/business-insights`) when:
- ✅ Quick analysis needed (< 40 seconds)
- ✅ Checking specific data source
- ✅ Testing new database connection
- ✅ Focused departmental insights
- ✅ Regular monitoring of one system
- ✅ Lower cost (2 LLM calls)

### Use **Project-Wide** (`/projects/{id}/business-insights`) when:
- ✅ Executive dashboard needed
- ✅ Strategic planning session
- ✅ Quarterly business review
- ✅ Cross-functional analysis required
- ✅ Need holistic view of all data
- ✅ Identifying cross-system opportunities
- ✅ Comprehensive data audit

---

## 🎯 Frontend Integration

### Single Database
```typescript
const { mutate, data, isLoading } = useMutation({
  mutationFn: (databaseId: string) =>
    axios.post('/api/v1/backend/business-insights', {
      database_connection_id: databaseId
    })
});

// Call it
mutate('550e8400-e29b-41d4-a716-446655440000');
```

### Project-Wide
```typescript
const { mutate, data, isLoading } = useMutation({
  mutationFn: (projectId: string) =>
    axios.post(`/api/v1/backend/projects/${projectId}/business-insights`)
});

// Call it  
mutate('2f96eace-5738-4c9f-afba-155203ee1434');
```

---

## ⚡ Performance

### Single Database
- **Time**: 12-35 seconds
- **LLM Calls**: 2
- **Cost**: ~$0.002-0.005 per request

### Project-Wide (3 databases example)
- **Time**: 45-115 seconds
- **LLM Calls**: 7 (2 per DB + 1 consolidation)
- **Cost**: ~$0.007-0.02 per request

---

## 🛡️ Error Handling

Both endpoints:
- ✅ Validate user authentication
- ✅ Check project access
- ✅ Handle database connection errors
- ✅ Continue on partial failures (project-wide)
- ✅ Return detailed error messages

---

## 📊 Response Fields Explained

### Consolidated Insights (Project-Wide Only)

**`overall_health_score`**
- `excellent`: All metrics strong, minimal risks
- `good`: Strong performance, some improvements needed
- `fair`: Mixed results, several concerns to address
- `poor`: Multiple critical issues requiring immediate action

**`strategic_priorities`**
- Ranked 1-5 by business impact
- Each includes title, description, and impact level
- Based on analysis across ALL databases

**`cross_database_patterns`**
- Correlations between different data sources
- Example: "Revenue growth correlates with customer acquisition"
- Helps identify systemic trends

**`risk_assessment`**
- **Critical**: Immediate attention required
- **Moderate**: Monitor and plan mitigation

**`opportunities`**
- Growth potential identified
- Includes estimated business impact
- Data-driven recommendations

---

## ✅ Summary

**Single Database Insights:**
- Fast, focused analysis
- 10 KPIs per database
- Tactical recommendations
- Perfect for regular monitoring

**Project-Wide Insights:**
- Comprehensive multi-database analysis
- Cross-system correlations
- Strategic recommendations
- Perfect for executive reporting

Both use **Gemini 2.5 Flash** for fast, accurate AI analysis!

