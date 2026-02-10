# Why Voice Biomarkers?

Text alone misses critical information. Voice carries physiological signals that reveal what words don't say.

## The Gap Between Words and Reality

In any voice conversation, there are two channels of information:

| Channel | What It Captures | Signal Reliability |
|---------|------------------|-------------------|
| **Text** | What someone says | Easily curated, minimized, or performative |
| **Voice Biomarkers** | How they say it | Physiological—reveals what words hide |

When these channels disagree, you learn something important.

## Cross-Domain Examples

### Contact Center: Frustrated but Polite

A customer says: *"It's fine, I understand these things happen."*

Text analysis: Positive sentiment, no escalation risk.

Voice biomarkers: Elevated stress (0.65), irritability (0.58), low happiness (0.12).

**The customer is frustrated but being polite.** Without voice biomarkers, this call gets marked as resolved. With them, you can proactively offer compensation or escalate to retention.

---

### Education: Confident Words, Anxious Voice

A language student says: *"Yeah, I think I understand. Let's try the next exercise."*

Text analysis: Ready to proceed.

Voice biomarkers: Anxiety probability (0.62), fear (0.28), low confidence indicators.

**The student is masking confusion to avoid embarrassment.** A tutor acting on text alone moves forward; one with biomarker insight pauses to check understanding.

---

### Mental Health: Minimization

A user says: *"My mood has been so-so, ups and downs. But I tried to remain positive."*

Text analysis: Mild concern at most.

Voice biomarkers: Depression probability (0.78), distress (0.81), elevated anhedonia.

**The user is minimizing significant distress.** This pattern is well-documented in clinical research: individuals in crisis frequently underreport symptoms.

---

### Employee Wellness: Surface Acting

A tutor says: *"No problem at all! Let's try it another way!"* (bright, encouraging tone)

Text analysis: Positive, engaged.

Voice biomarkers: Burnout (0.62), stress (0.68), fatigue (0.60).

**The employee is performing positivity while exhausted.** This "surface acting" accelerates burnout. Early detection enables intervention before they quit.

---

### Coaching: Hidden Resistance

A coaching client says: *"That's a good idea. I'll definitely try that."*

Text analysis: Agreement, commitment.

Voice biomarkers: Low engagement (0.25), elevated stress (0.45), flat affect.

**The client is agreeing to end the conversation, not because they're convinced.** A coach with this insight can probe deeper rather than assuming buy-in.

## The Concordance Framework

Sentinel performs explicit concordance analysis between text and voice:

| Pattern | Text Signal | Voice Signal | Interpretation |
|---------|-------------|--------------|----------------|
| **Concordance** | Positive | Calm/happy | Genuine positive state |
| **Concordance** | Negative | Distressed | Acknowledged difficulty |
| **Minimization** | Positive | Distressed | Masking or poor insight |
| **Amplification** | Negative | Calm | Venting without crisis |

This concordance signal is what enables Sentinel to reduce both false positives (flagging venting as crisis) and false negatives (missing masked distress).

## Why This Matters for Voice AI

Voice AI systems are increasingly handling sensitive conversations: healthcare triage, customer support, coaching, education, mental health. These systems need to:

1. **Detect when users aren't saying what they mean** — minimization, politeness, performance
2. **Avoid over-reacting to language patterns** — "I'm dying of embarrassment" isn't a crisis
3. **Provide ground truth for ambiguous situations** — when text alone is insufficient

Voice biomarkers provide the physiological layer that makes this possible.

## Research Foundation

The biomarker models are clinical-grade, validated against gold-standard clinical assessments. See the [Nature Portfolio publication](https://rdcu.be/e24Jk) for Apollo validation and the [Interspeech 2025 paper](https://arxiv.org/abs/2505.23378) for related research.

See [Biomarkers](biomarkers.md) for the full list of available biomarkers.
