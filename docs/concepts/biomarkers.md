# Biomarkers

Sentinel extracts speech biomarkers from voice audio through specialized models. Each model targets different aspects of mental and physical state, with varying levels of clinical validation.

## Biomarker Models

### Apollo — Clinical Mental Health
:material-check-decagram:{ .production title="Production" } **Production** :material-flask:{ .clinical title="Clinical Grade" } **Clinical Grade**

**Domains:** Clinical, Mental Health, Employee Wellness, Education, Coaching

Disorder probabilities and symptom-level severities, validated against clinical gold standards. [Published in Nature Portfolio](https://rdcu.be/e24Jk).

**Disorder Probabilities:**

| Biomarker | Description | Range | Use Cases |
|-----------|-------------|-------|-----------|
| `depression_probability` | Likelihood of depression | 0-1 | Mental health screening, employee wellness, student support |
| `anxiety_probability` | Likelihood of anxiety disorder | 0-1 | Test prep, public speaking, sales calls, interviews |

**Depression Indicators (PHQ-9 aligned):** :material-flask:{ .clinical title="Clinical Grade" } **Clinical Grade**

| Biomarker | Description | Range | Beyond Clinical Use |
|-----------|-------------|-------|---------------------|
| `anhedonia` | Loss of interest/pleasure | 0-1 | Employee engagement, coaching motivation |
| `low_mood` | Depressed mood | 0-1 | Wellness monitoring, student mental health |
| `sleep_issues` | Sleep disturbance | 0-1 | Fatigue risk, shift worker wellness |
| `low_energy` | Fatigue/loss of energy | 0-1 | Workplace safety, sports performance |
| `appetite` | Appetite changes | 0-1 | Health screening, wellness programs |
| `worthlessness` | Feelings of worthlessness | 0-1 | Coaching, leadership development |
| `concentration` | Difficulty concentrating | 0-1 | Education, workplace productivity |
| `psychomotor` | Psychomotor changes | 0-1 | Clinical assessment |

**Anxiety Indicators (GAD-7 aligned):** :material-flask:{ .clinical title="Clinical Grade" } **Clinical Grade**

| Biomarker | Description | Range | Beyond Clinical Use |
|-----------|-------------|-------|---------------------|
| `nervousness` | Feeling nervous/anxious | 0-1 | Presentations, interviews, sales calls |
| `uncontrollable_worry` | Can't stop worrying | 0-1 | Stress monitoring, coaching |
| `excessive_worry` | Worrying too much | 0-1 | Employee wellness, education |
| `trouble_relaxing` | Difficulty relaxing | 0-1 | Burnout detection, wellness |
| `restlessness` | Restless/on edge | 0-1 | Meeting engagement, education |
| `irritability` | Easily annoyed | 0-1 | Contact centers, customer experience, escalation prediction |
| `dread` | Sense of impending doom | 0-1 | Crisis detection, mental health |

---

### Helios — Wellness Indicators
:material-check-decagram:{ .production title="Production" } **Production**

**Domains:** Wellness, Workplace, Contact Centers, Education, Coaching, HR

General wellness scores derived from voice characteristics. Uses similar technology to Apollo. [Research published at Interspeech 2025](https://arxiv.org/abs/2505.23378).

| Biomarker | Description | Range | Use Cases |
|-----------|-------------|-------|-----------|
| `distress` | Overall psychological distress | 0-1 | Crisis detection, customer experience, employee wellness |
| `stress` | Acute stress level | 0-1 | Contact centers, workplace, coaching, sports performance |
| `burnout` | Chronic exhaustion indicators | 0-1 | HR/retention, education, healthcare workers |
| `fatigue` | Physical and mental tiredness | 0-1 | Shift work safety, transportation, healthcare |
| `low_self_esteem` | Self-worth indicators | 0-1 | Coaching, education, leadership development |

---

### Psyche — Real-Time Affect
:material-beta:{ .beta title="Beta" } **Beta**

**Domains:** All (real-time emotion tracking)

Moment-to-moment emotional state from voice. Updates every ~5 seconds, providing real-time signal for live applications.

| Biomarker | Description | Range | Use Cases |
|-----------|-------------|-------|-----------|
| `neutral` | Flat/neutral affect | 0-1 | Baseline reference |
| `happy` | Joy/happiness | 0-1 | Engagement, satisfaction, coaching success |
| `sad` | Sadness | 0-1 | Customer experience, mental health |
| `angry` | Anger/frustration | 0-1 | Contact center escalation, conflict detection |
| `fearful` | Fear/anxiety in voice | 0-1 | Education anxiety, crisis detection |
| `disgusted` | Disgust | 0-1 | Content reaction |
| `surprised` | Surprise | 0-1 | Context-dependent |

---

### Focus — Attention Tracking
:material-clock-outline:{ .coming-soon title="Coming Soon" } **Coming Soon**

**Domains:** Education, Workplace, ADHD Support, Gaming

Attention and focus metrics calibrated for ADHD-aware applications.

| Biomarker | Description | Range | Use Cases |
|-----------|-------------|-------|-----------|
| `focus` | Overall focus level | 0-1 | Education, workplace productivity |
| `attention` | Sustained attention | 0-1 | Learning, meeting engagement |
| `distractibility` | Distraction indicator | 0-1 | ADHD support, driving safety |

---

### Diabetes Type 2 Screening
:material-clock-outline:{ .coming-soon title="Coming Soon" } **Coming Soon**

**Domains:** Healthcare, Telehealth, Wellness Programs

Voice-based screening indicator for Type 2 diabetes risk.

---

### COPD Screening
:material-clock-outline:{ .coming-soon title="Coming Soon" } **Coming Soon**

**Domains:** Healthcare, Telehealth, Respiratory Health

Voice-based screening indicator for COPD.

---

## Configuration

Specify which biomarker models to enable:

```python
sentinel = SentinelClient(
    # ... other config
    biomarkers=["helios", "apollo", "psyche"],
)
```

!!! note "Processing Requirements"
    Different biomarkers require different amounts of speech data. Psyche provides results fastest (~5s), followed by Helios (~10s), with Apollo requiring more speech (~20s) for accurate predictions. These thresholds may vary based on your policy configuration.

## Progress Updates

Track biomarker collection progress:

```python
@sentinel.on_progress
def handle_progress(result):
    for name, status in result["biomarkers"].items():
        collected = status["speech_seconds"]
        required = status["trigger_seconds"]
        pct = (collected / required) * 100
        print(f"{name}: {pct:.0f}%")
```

## Validation

Apollo biomarkers are clinical-grade, validated against gold-standard clinical assessments. See the [Nature Portfolio publication](https://rdcu.be/e24Jk) for validation methodology and results.

Helios wellness biomarkers use similar underlying technology. See the [Interspeech 2025 paper](https://arxiv.org/abs/2505.23378) for research details.

Clinical-grade means rigorous validation—but the biomarkers are useful far beyond clinical settings: employee wellness, education, customer experience, and anywhere voice reveals what words don't say.
