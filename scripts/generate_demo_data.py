"""Generate a synthetic demo dataset + render the dashboard, for screenshots / blog posts.

No real client data, no live crawl, no LLM calls. Hardcoded fictional brand
("Lumenflow" — a made-up B2B SaaS product analytics platform) with believable
clusters, cannibalization, content ideas, competitors, brand voice, etc.

Usage:
    cd /Users/gmejia/topical-authority-mapper
    source venv/bin/activate
    python scripts/generate_demo_data.py
    open output-demo/dashboard.html
"""

import csv
import json
import os
import random
import shutil
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEMO_OUTPUT = os.path.join(ROOT, "output-demo")
DEMO_CACHE = os.path.join(ROOT, "cache-demo")
random.seed(42)

# ---------------------------------------------------------------------------
# Synthetic site
# ---------------------------------------------------------------------------

SITE_NAME = "Lumenflow"
SITE_DOMAIN = "lumenflow.demo"
SITE_INDUSTRY = "b2b-saas"
COMPETITORS = ["BeaconAnalytics", "PulseGrid", "Insightspark"]

# 30 realistic cluster names for a B2B product-analytics company
CLUSTERS = [
    {"id": 0, "name": "Customer Analytics Platform", "keywords": "customer analytics, behavioral data, user insights, analytics platform, customer intelligence, data-driven decisions"},
    {"id": 1, "name": "Product Telemetry", "keywords": "product telemetry, event tracking, telemetry data, instrumentation, sdk integration, event schema"},
    {"id": 2, "name": "User Behavior Tracking", "keywords": "user behavior, behavior tracking, click tracking, user journey, behavior analytics, session tracking"},
    {"id": 3, "name": "Funnel Analysis", "keywords": "funnel analysis, conversion funnel, drop-off rates, funnel optimization, multi-step funnel, funnel visualization"},
    {"id": 4, "name": "Cohort Reporting", "keywords": "cohort analysis, cohort reporting, retention cohorts, cohort metrics, behavioral cohorts, time-based cohorts"},
    {"id": 5, "name": "Retention Metrics", "keywords": "retention metrics, user retention, customer retention, retention curves, dau mau ratio, repeat usage"},
    {"id": 6, "name": "Onboarding Optimization", "keywords": "onboarding flow, user onboarding, activation metrics, onboarding optimization, time to value, first session"},
    {"id": 7, "name": "Feature Adoption", "keywords": "feature adoption, feature usage, adoption rate, feature analytics, power users, sticky features"},
    {"id": 8, "name": "Churn Prediction", "keywords": "churn prediction, churn analysis, predictive churn, churn risk, retention modeling, customer health score"},
    {"id": 9, "name": "A/B Testing Framework", "keywords": "ab testing, experiment design, split testing, statistical significance, hypothesis testing, conversion experiments"},
    {"id": 10, "name": "Event Schema Design", "keywords": "event schema, event taxonomy, event naming, tracking plan, schema design, event properties"},
    {"id": 11, "name": "Session Replay", "keywords": "session replay, session recording, user session playback, screen recording, behavioral replay, ux debugging"},
    {"id": 12, "name": "Privacy Compliance", "keywords": "privacy compliance, gdpr analytics, ccpa, data anonymization, consent management, privacy by design"},
    {"id": 13, "name": "Data Pipeline Architecture", "keywords": "data pipeline, etl pipeline, real-time pipeline, data ingestion, streaming analytics, pipeline architecture"},
    {"id": 14, "name": "Dashboard Building", "keywords": "dashboard building, kpi dashboard, custom dashboards, data visualization, executive dashboards, dashboard design"},
    {"id": 15, "name": "Self-Serve Analytics", "keywords": "self-serve analytics, no-code analytics, self-service bi, ad-hoc analysis, citizen data analyst, democratize data"},
    {"id": 16, "name": "Mobile App Analytics", "keywords": "mobile analytics, app analytics, ios analytics, android tracking, mobile sdk, app engagement"},
    {"id": 17, "name": "Web Analytics", "keywords": "web analytics, website tracking, page analytics, traffic analytics, web events, browser events"},
    {"id": 18, "name": "E-commerce Tracking", "keywords": "ecommerce tracking, purchase events, cart analytics, checkout funnel, ecommerce metrics, transaction tracking"},
    {"id": 19, "name": "Marketing Attribution", "keywords": "marketing attribution, multi-touch attribution, attribution modeling, channel attribution, mta, attribution analytics"},
    {"id": 20, "name": "Product-Led Growth", "keywords": "product led growth, plg, plg metrics, product qualified leads, pql, free to paid conversion"},
    {"id": 21, "name": "Customer Journey Mapping", "keywords": "customer journey, journey mapping, journey analytics, lifecycle stages, customer touchpoints, journey orchestration"},
    {"id": 22, "name": "Voice of Customer", "keywords": "voice of customer, voc, customer feedback, in-app surveys, nps surveys, customer sentiment"},
    {"id": 23, "name": "NPS Tracking", "keywords": "nps tracking, net promoter score, nps surveys, promoter detractor, nps benchmarks, customer loyalty"},
    {"id": 24, "name": "Heatmaps", "keywords": "heatmaps, click heatmaps, scroll maps, attention maps, heatmap analytics, ui hotspots"},
    {"id": 25, "name": "Personalization Engine", "keywords": "personalization, dynamic content, behavioral personalization, recommendation engine, ai personalization, segmentation"},
    {"id": 26, "name": "Push Notification Strategy", "keywords": "push notifications, push strategy, mobile push, push automation, notification timing, push engagement"},
    {"id": 27, "name": "Email Engagement", "keywords": "email engagement, email analytics, open rates, click rates, lifecycle emails, behavioral email"},
    {"id": 28, "name": "Conversion Optimization", "keywords": "conversion rate optimization, cro, conversion analytics, landing page optimization, conversion testing, optimization framework"},
    {"id": 29, "name": "SaaS Metrics", "keywords": "saas metrics, mrr, arr, cac, ltv, expansion revenue, net revenue retention"},
]

# How many URLs each cluster owns (varied sizes for a nice treemap)
CLUSTER_URL_COUNTS = [12, 8, 11, 7, 6, 9, 5, 7, 4, 10, 6, 5, 4, 6, 8, 7, 5, 6, 4, 7, 9, 5, 4, 4, 5, 4, 3, 5, 8, 6]

# Cannibalized clusters (cluster_id, num_competing_urls, severity, has_conv_risk, llm_verdict)
# llm_verdict: "REAL" or "FALSE_POSITIVE"
CANNIB = [
    {"cid": 0, "count": 12, "is_real": True, "advisor_reason": "All 12 URLs target 'customer analytics platform' as primary intent — competing for the same head term. Recommend pillar consolidation."},
    {"cid": 2, "count": 11, "is_real": True, "advisor_reason": "10 informational posts plus 1 service page all target 'user behavior tracking' / 'behavior analytics'. Conversion risk: blogs may outrank the service page."},
    {"cid": 9, "count": 10, "is_real": True, "advisor_reason": "Multiple how-to guides on the same A/B testing framework with overlapping keywords. Merge into 1 pillar + 3 angle-specific spokes."},
    {"cid": 3, "count": 7, "is_real": True, "advisor_reason": "Funnel analysis pages with near-identical keyword targeting. Consolidate to strengthen pillar authority."},
    {"cid": 5, "count": 9, "is_real": False, "advisor_reason": "Mixed page types (1 service page + 1 customer story + 1 webinar lander + 6 blog posts). Different intents — TF-IDF false positive, not real cannibalization."},
    {"cid": 7, "count": 7, "is_real": False, "advisor_reason": "Includes 1 product feature lander, 1 case study, and 5 blog posts on adjacent but distinct angles. Reclassify."},
    {"cid": 14, "count": 8, "is_real": True, "advisor_reason": "Eight blog posts covering overlapping dashboard-building tutorials. Merge into 1 comprehensive guide + 2 use-case-specific spokes."},
    {"cid": 28, "count": 8, "is_real": False, "advisor_reason": "Pages span CRO basics, advanced testing, and a benchmark report. Distinct sub-topics — reclassify under a CRO pillar with 3 sub-clusters instead of treating as competing."},
]

# 40 content ideas with varied priorities, audiences, content types
CONTENT_IDEAS = [
    # P1 (validated by 2+ competitors) — 5 ideas
    {"priority": "P1", "title": "Best Customer Data Platform: A B2B SaaS Product Marketing Buyer's Guide", "topic": "best customer data platform", "type": "Comparison page", "intent": "comparison", "audience": "Product marketing + RevOps teams", "words": 2500, "covered_by": "BeaconAnalytics, PulseGrid", "n_comp": 2, "spoke": "Customer Analytics Platform", "spoke_sim": 0.612, "kws": "best customer data platform | customer data platform alternatives | top customer data platforms", "questions": "Who are the top alternatives for customer data platform? | How do they differ on pricing, integrations, ideal use case? | Which option fits B2B SaaS teams of different sizes? | What's the strongest case for picking the runner-up over the leader? | What concise definition would an LLM cite for 'customer data platform'? | What 6-10 People-Also-Ask questions does Google currently surface? | What schema.org markup is appropriate (FAQPage, Product)? | Which 3-5 authoritative sources should you cite? | What internal pages should you link from + to?"},
    {"priority": "P1", "title": "How to Build a Tracking Plan: A Practical Guide for Product + Engineering Teams", "topic": "tracking plan", "type": "How-to guide", "intent": "howto", "audience": "Product + engineering teams", "words": 1800, "covered_by": "BeaconAnalytics, Insightspark", "n_comp": 2, "spoke": "Event Schema Design", "spoke_sim": 0.587, "kws": "tracking plan | how to build a tracking plan | tracking plan template", "questions": "What's the step-by-step process for building a tracking plan? | What are common mistakes to avoid? | What templates and tools cut the time in half? | What does 'before vs after' look like with real numbers? | What concise definition for 'tracking plan' would an LLM cite? | What People-Also-Ask questions does Google surface? | What schema.org markup applies (HowTo, Article)? | Which authoritative sources should you cite? | What internal pages link from + to?"},
    {"priority": "P1", "title": "The JTBD Framework: How Product Teams Use It for Activation", "topic": "jtbd framework", "type": "Framework explainer", "intent": "framework", "audience": "Product + UX research teams", "words": 1500, "covered_by": "PulseGrid, Insightspark", "n_comp": 2, "spoke": "Onboarding Optimization", "spoke_sim": 0.501, "kws": "jtbd framework | jobs to be done framework | jtbd model", "questions": "What is the JTBD framework, who originated it, and what problem does it solve? | When should a team apply it? When should they avoid it? | What are the steps + outputs at each stage? | What does a worked example look like end-to-end? | What concise definition for 'jtbd framework' would an LLM cite? | What PAA questions does Google surface? | What schema.org markup applies? | Which authoritative sources to cite? | What internal pages link from + to?"},
    {"priority": "P1", "title": "Activation Rate Benchmarks: What B2B SaaS Product Teams Should Be Hitting", "topic": "activation rate benchmarks", "type": "Benchmark + data report", "intent": "metrics", "audience": "Product-led growth teams", "words": 1400, "covered_by": "BeaconAnalytics, PulseGrid", "n_comp": 2, "spoke": "Onboarding Optimization", "spoke_sim": 0.638, "kws": "activation rate benchmarks | average activation rate | b2b saas activation benchmark", "questions": "What are the current benchmarks for activation rate? | How do top-quartile teams compare to median? | How does this benchmark vary by company size, industry, GTM motion? | What's the right cadence to measure and recalibrate? | What concise definition would an LLM cite? | What PAA questions does Google surface? | What schema.org applies? | Which sources to cite? | What internal pages to link?"},
    {"priority": "P1", "title": "What Is Product-Qualified Lead (PQL)? A Complete Guide for PLG Teams", "topic": "what is pql", "type": "Pillar / definitive guide", "intent": "definition", "audience": "Product-led growth teams", "words": 2000, "covered_by": "PulseGrid, BeaconAnalytics", "n_comp": 2, "spoke": "Product-Led Growth", "spoke_sim": 0.722, "kws": "what is pql | product qualified lead | pql definition", "questions": "What does 'PQL' actually mean (and what isn't it)? | Why does it matter for PLG teams right now? | How do leading teams use it in practice — with one named example? | What's the most common misconception worth correcting upfront? | What concise LLM-citable definition? | What PAA questions does Google surface? | What schema.org? | Which sources to cite? | What internal pages?"},
    # P2 (1 competitor, mostly with spoke matches) — 18 ideas
    {"priority": "P2", "title": "How to Set Up Funnel Analysis: A Practical Guide for Product Marketing + Content Teams", "topic": "funnel analysis setup", "type": "How-to guide", "intent": "howto", "audience": "Product marketing + content teams", "words": 1800, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Funnel Analysis", "spoke_sim": 0.701, "kws": "funnel analysis setup | how to set up funnel | conversion funnel tutorial", "questions": "What's the step-by-step process? | Common mistakes to avoid? | Templates and tools that help? | Before/after numbers? | LLM-citable definition? | PAA questions? | Schema.org? | Sources to cite? | Internal links?"},
    {"priority": "P2", "title": "The Cohort Analysis Framework: How Product Teams Use It", "topic": "cohort analysis framework", "type": "Framework explainer", "intent": "framework", "audience": "Product + UX research teams", "words": 1500, "covered_by": "Insightspark", "n_comp": 1, "spoke": "Cohort Reporting", "spoke_sim": 0.689, "kws": "cohort analysis framework | cohort framework | cohort model", "questions": "What is the cohort framework? | When to apply / avoid? | Steps + outputs at each stage? | Worked example? | LLM definition? | PAA questions? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "Best Session Replay Tools: A B2B SaaS Buyer's Guide", "topic": "best session replay tools", "type": "Comparison page", "intent": "comparison", "audience": "Product marketing + content teams", "words": 2500, "covered_by": "PulseGrid", "n_comp": 1, "spoke": "Session Replay", "spoke_sim": 0.598, "kws": "best session replay tools | session replay alternatives | top session replay", "questions": "Top alternatives? | How do they differ on pricing/features/use case? | Which fits SMB / mid-market / enterprise? | Strongest case for the runner-up? | LLM-citable summary? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "Churn Rate Benchmarks: What SaaS Product Teams Should Be Hitting", "topic": "churn rate benchmarks", "type": "Benchmark + data report", "intent": "metrics", "audience": "Customer success + retention teams", "words": 1400, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Churn Prediction", "spoke_sim": 0.654, "kws": "churn rate benchmarks | average churn rate | b2b saas churn benchmark", "questions": "Current benchmarks (top-quartile, median, bottom)? | What drives the gap? | Variation by size/industry/motion? | Right cadence to measure? | LLM definition? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "How to Run an A/B Test: A Practical Guide for Growth + Product Teams", "topic": "how to run ab test", "type": "How-to guide", "intent": "howto", "audience": "Growth + product teams", "words": 1800, "covered_by": "Insightspark", "n_comp": 1, "spoke": "A/B Testing Framework", "spoke_sim": 0.711, "kws": "how to run ab test | ab testing tutorial | split testing guide", "questions": "Step-by-step? | Mistakes to avoid? | Templates? | Before/after? | LLM definition? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "What Is Product Telemetry? A Complete Guide for Product + Engineering Teams", "topic": "what is product telemetry", "type": "Pillar / definitive guide", "intent": "definition", "audience": "Product + engineering teams", "words": 2000, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Product Telemetry", "spoke_sim": 0.812, "kws": "what is product telemetry | product telemetry definition | telemetry for products", "questions": "What does it mean (and what isn't it)? | Why does it matter now? | How do leading teams use it? | Common misconception? | LLM definition? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "Best Heatmap Tools: A Conversion Optimization Buyer's Guide", "topic": "best heatmap tools", "type": "Comparison page", "intent": "comparison", "audience": "Analytics + growth teams", "words": 2500, "covered_by": "PulseGrid", "n_comp": 1, "spoke": "Heatmaps", "spoke_sim": 0.624, "kws": "best heatmap tools | heatmap alternatives | top heatmap software", "questions": "Top alternatives? | How do they differ? | Best fit by size? | Runner-up case? | LLM summary? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "How to Build an NPS Tracking Program: A Practical Guide for Customer Success + Retention Teams", "topic": "how to build nps tracking", "type": "How-to guide", "intent": "howto", "audience": "Customer success + retention teams", "words": 1800, "covered_by": "Insightspark", "n_comp": 1, "spoke": "NPS Tracking", "spoke_sim": 0.731, "kws": "how to build nps tracking | nps tracking program | nps survey setup", "questions": "Step-by-step? | Mistakes? | Templates? | Before/after? | LLM def? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "What Is Marketing Attribution? A Complete Guide for Marketing + Growth Teams", "topic": "what is marketing attribution", "type": "Pillar / definitive guide", "intent": "definition", "audience": "Marketing + growth teams", "words": 2000, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Marketing Attribution", "spoke_sim": 0.798, "kws": "what is marketing attribution | marketing attribution definition | attribution explained", "questions": "What does it mean? | Why does it matter? | How do leading teams use it? | Misconception? | LLM def? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "The Product Adoption Framework: How SaaS Product Teams Use It", "topic": "product adoption framework", "type": "Framework explainer", "intent": "framework", "audience": "Product-led growth teams", "words": 1500, "covered_by": "PulseGrid", "n_comp": 1, "spoke": "Feature Adoption", "spoke_sim": 0.682, "kws": "product adoption framework | adoption framework | feature adoption model", "questions": "What is the framework? | When to apply/avoid? | Steps + outputs? | Worked example? | LLM def? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "Conversion Rate Benchmarks: What Growth Teams Should Be Hitting", "topic": "conversion rate benchmarks", "type": "Benchmark + data report", "intent": "metrics", "audience": "Growth + product teams", "words": 1400, "covered_by": "Insightspark", "n_comp": 1, "spoke": "Conversion Optimization", "spoke_sim": 0.701, "kws": "conversion rate benchmarks | average conversion rate | b2b saas conversion benchmark", "questions": "Current benchmarks? | Top-quartile vs median? | Variation by size/industry? | Cadence? | LLM def? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "How to Implement Customer Journey Mapping: A Practical Guide", "topic": "customer journey mapping implementation", "type": "How-to guide", "intent": "howto", "audience": "Product + UX research teams", "words": 1800, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Customer Journey Mapping", "spoke_sim": 0.769, "kws": "customer journey mapping implementation | implement customer journey | journey mapping setup", "questions": "Step-by-step? | Mistakes? | Templates? | Before/after? | LLM def? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "Best Mobile Analytics Tools: A B2B SaaS Buyer's Guide", "topic": "best mobile analytics tools", "type": "Comparison page", "intent": "comparison", "audience": "Mobile product + growth teams", "words": 2500, "covered_by": "PulseGrid", "n_comp": 1, "spoke": "Mobile App Analytics", "spoke_sim": 0.732, "kws": "best mobile analytics tools | mobile analytics alternatives | top mobile analytics", "questions": "Top alternatives? | How do they differ? | Best fit by size? | Runner-up case? | LLM summary? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "What Is Self-Serve Analytics? A Complete Guide for Data + Operations Teams", "topic": "what is self-serve analytics", "type": "Pillar / definitive guide", "intent": "definition", "audience": "Data + analytics ops teams", "words": 2000, "covered_by": "Insightspark", "n_comp": 1, "spoke": "Self-Serve Analytics", "spoke_sim": 0.821, "kws": "what is self-serve analytics | self-serve analytics definition | self-service bi explained", "questions": "What does it mean? | Why does it matter? | Leading teams' usage? | Misconception? | LLM def? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "The Voice of Customer Framework: How Product Teams Use It", "topic": "voice of customer framework", "type": "Framework explainer", "intent": "framework", "audience": "Product marketing + content teams", "words": 1500, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Voice of Customer", "spoke_sim": 0.788, "kws": "voice of customer framework | voc framework | voc model", "questions": "What's the framework? | When to apply/avoid? | Steps + outputs? | Worked example? | LLM def? | PAA? | Schema.org? | Sources? | Internal links?"},
    {"priority": "P2", "title": "How to Set Up Email Engagement Tracking: A Practical Guide for Lifecycle Teams", "topic": "email engagement tracking setup", "type": "How-to guide", "intent": "howto", "audience": "Lifecycle marketing teams", "words": 1800, "covered_by": "PulseGrid", "n_comp": 1, "spoke": "Email Engagement", "spoke_sim": 0.694, "kws": "email engagement tracking setup | email tracking guide | email analytics setup", "questions": "Step-by-step? | Mistakes? | Templates? | Before/after? | LLM def? | PAA? | Schema.org? | Sources? | Internal links?"},
    # P3 (single competitor, no spoke or weak spoke) — 17 ideas
    {"priority": "P3", "title": "The Complete Guide to Push Notification Strategy for Mobile Product Teams", "topic": "push notification strategy", "type": "Pillar guide", "intent": "guide", "audience": "Mobile product + growth teams", "words": 1500, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Push Notification Strategy", "spoke_sim": 0.812, "kws": "push notification strategy", "questions": "What is it? | Why does it matter? | Common approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Heatmap Analytics for Conversion Optimization Teams", "topic": "heatmap analytics", "type": "Pillar guide", "intent": "guide", "audience": "Analytics + growth teams", "words": 1500, "covered_by": "PulseGrid", "n_comp": 1, "spoke": "Heatmaps", "spoke_sim": 0.674, "kws": "heatmap analytics", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Cohort Reporting for Product Teams", "topic": "cohort reporting", "type": "Pillar guide", "intent": "guide", "audience": "Product + UX research teams", "words": 1500, "covered_by": "Insightspark", "n_comp": 1, "spoke": "Cohort Reporting", "spoke_sim": 0.752, "kws": "cohort reporting", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Behavioral Segmentation", "topic": "behavioral segmentation", "type": "Pillar guide", "intent": "guide", "audience": "Marketing + growth teams", "words": 1500, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Personalization Engine", "spoke_sim": 0.541, "kws": "behavioral segmentation", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Multi-Touch Attribution Modeling", "topic": "multi-touch attribution modeling", "type": "Pillar guide", "intent": "guide", "audience": "Marketing + growth teams", "words": 1500, "covered_by": "PulseGrid", "n_comp": 1, "spoke": "Marketing Attribution", "spoke_sim": 0.698, "kws": "multi-touch attribution modeling", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Customer Health Scoring", "topic": "customer health scoring", "type": "Pillar guide", "intent": "guide", "audience": "Customer success + retention teams", "words": 1500, "covered_by": "Insightspark", "n_comp": 1, "spoke": "Churn Prediction", "spoke_sim": 0.521, "kws": "customer health scoring", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Real-Time Streaming Analytics", "topic": "real-time streaming analytics", "type": "Pillar guide", "intent": "guide", "audience": "Data + analytics ops teams", "words": 1500, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Data Pipeline Architecture", "spoke_sim": 0.643, "kws": "real-time streaming analytics", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Reverse ETL", "topic": "reverse etl", "type": "Pillar guide", "intent": "guide", "audience": "Data + analytics ops teams", "words": 1500, "covered_by": "PulseGrid", "n_comp": 1, "spoke": "Data Pipeline Architecture", "spoke_sim": 0.612, "kws": "reverse etl", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Activation Metrics for SaaS Teams", "topic": "activation metrics", "type": "Pillar guide", "intent": "guide", "audience": "Product-led growth teams", "words": 1500, "covered_by": "Insightspark", "n_comp": 1, "spoke": "Onboarding Optimization", "spoke_sim": 0.589, "kws": "activation metrics", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Dau Mau Ratio Tracking", "topic": "dau mau ratio tracking", "type": "Pillar guide", "intent": "guide", "audience": "Product-led growth teams", "words": 1500, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Retention Metrics", "spoke_sim": 0.671, "kws": "dau mau ratio tracking", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Onboarding Funnel Optimization", "topic": "onboarding funnel optimization", "type": "Pillar guide", "intent": "guide", "audience": "Product-led growth teams", "words": 1500, "covered_by": "PulseGrid", "n_comp": 1, "spoke": "Onboarding Optimization", "spoke_sim": 0.789, "kws": "onboarding funnel optimization", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to GDPR-Compliant Analytics", "topic": "gdpr-compliant analytics", "type": "Pillar guide", "intent": "guide", "audience": "Data + privacy teams", "words": 1500, "covered_by": "Insightspark", "n_comp": 1, "spoke": "Privacy Compliance", "spoke_sim": 0.732, "kws": "gdpr-compliant analytics", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to In-App Surveys", "topic": "in-app surveys", "type": "Pillar guide", "intent": "guide", "audience": "Product marketing + content teams", "words": 1500, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Voice of Customer", "spoke_sim": 0.621, "kws": "in-app surveys", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Funnel Drop-Off Analysis", "topic": "funnel drop-off analysis", "type": "Pillar guide", "intent": "guide", "audience": "Growth + product teams", "words": 1500, "covered_by": "PulseGrid", "n_comp": 1, "spoke": "Funnel Analysis", "spoke_sim": 0.812, "kws": "funnel drop-off analysis", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Free-to-Paid Conversion Tracking", "topic": "free-to-paid conversion tracking", "type": "Pillar guide", "intent": "guide", "audience": "Product-led growth teams", "words": 1500, "covered_by": "Insightspark", "n_comp": 1, "spoke": "Product-Led Growth", "spoke_sim": 0.701, "kws": "free-to-paid conversion tracking", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Time-to-Value Measurement", "topic": "time-to-value measurement", "type": "Pillar guide", "intent": "guide", "audience": "Product-led growth teams", "words": 1500, "covered_by": "BeaconAnalytics", "n_comp": 1, "spoke": "Onboarding Optimization", "spoke_sim": 0.642, "kws": "time-to-value measurement", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
    {"priority": "P3", "title": "The Complete Guide to Product-Led SEO Strategy", "topic": "product-led seo strategy", "type": "Pillar guide", "intent": "guide", "audience": "Marketing + growth teams", "words": 1500, "covered_by": "PulseGrid", "n_comp": 1, "spoke": "Product-Led Growth", "spoke_sim": 0.612, "kws": "product-led seo strategy", "questions": "What? | Why? | Approaches? | Best-in-class? | Failure mode?"},
]


def write_csv(path, rows, columns=None):
    if not rows:
        # Write empty file with header if columns provided
        with open(path, "w", newline="") as f:
            if columns:
                csv.writer(f).writerow(columns)
        return
    cols = columns or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def slugify(s):
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-").replace("--", "-")


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def gen_clusters():
    return [
        {"cluster_id": c["id"], "cluster_name": c["name"], "keywords": c["keywords"]}
        for c in CLUSTERS
    ]


def gen_url_mapping():
    rows = []
    seq = 1
    for c, n in zip(CLUSTERS, CLUSTER_URL_COUNTS):
        cid = c["id"]
        slug_root = slugify(c["name"])
        for i in range(n):
            # Mix of post / guide / case-study / service URL shapes
            shapes = [
                f"https://{SITE_DOMAIN}/post/{slug_root}-tutorial-{i+1}",
                f"https://{SITE_DOMAIN}/blog/{slug_root}-best-practices",
                f"https://{SITE_DOMAIN}/guide/{slug_root}-explained",
                f"https://{SITE_DOMAIN}/post/how-to-{slug_root}-{i+1}",
                f"https://{SITE_DOMAIN}/case-study/{slug_root}-{['acme','globex','initech','sterling','umbrella'][i % 5]}",
            ]
            url = shapes[i % len(shapes)]
            secondary = ""
            # Add a spoke (secondary) cluster ID for ~30% of pages
            if random.random() < 0.3:
                secondary = str((cid + 7) % len(CLUSTERS))
            rows.append({
                "url": url,
                "main_cluster": cid,
                "cluster_name": c["name"],
                "secondary_clusters": secondary,
            })
            seq += 1
    # Add a few "unclustered" orphan URLs
    for i in range(8):
        rows.append({
            "url": f"https://{SITE_DOMAIN}/orphan-page-{i+1}",
            "main_cluster": -1,
            "cluster_name": "",
            "secondary_clusters": "",
        })
    return rows


def gen_cannibalization(url_map):
    rows = []
    for c in CANNIB:
        cluster_urls = [u["url"] for u in url_map if u["main_cluster"] == c["cid"]][: c["count"]]
        rows.append({
            "cluster_id": c["cid"],
            "cluster_name": CLUSTERS[c["cid"]]["name"],
            "url_count": len(cluster_urls),
            "urls": " | ".join(cluster_urls),
            "recommendation": "Critical: significant topic overlap — consolidate aggressively, keep 1-2 pages max" if c["count"] >= 10 else "High priority: merge weaker pages into strongest performer, redirect others",
        })
    return rows


def gen_skipped_urls():
    rows = []
    # 12 thin pages — mix of categories
    thin_pages = [
        ("/blog/short-update-q1-recap", 184, "blog"),
        ("/blog/quick-product-news", 142, "blog"),
        ("/post/customer-spotlight-stub", 98, "blog"),
        ("/services/integration-consulting", 218, "service"),
        ("/services/data-migration", 156, "service"),
        ("/case-study/empty-stub", 87, "case-study"),
        ("/industries/healthcare", 124, "industry"),
        ("/industries/fintech", 162, "industry"),
        ("/guide/getting-started-stub", 78, "guide"),
        ("/author/sam-rivera", 94, "author"),
        ("/author/priya-shah", 112, "author"),
        ("/post/release-notes-2026-04", 105, "blog"),
    ]
    for slug, words, _kind in thin_pages:
        rows.append({"url": f"https://{SITE_DOMAIN}{slug}", "reason": f"thin content ({words} words)"})
    # Also add some intentionally-thin pages (will be filtered by is_intentionally_thin)
    for slug in ["/pricing", "/login", "/signup", "/games/quiz", "/customers", "/integrations", "/legal/privacy"]:
        rows.append({"url": f"https://{SITE_DOMAIN}{slug}", "reason": f"thin content ({random.randint(20, 150)} words)"})
    return rows


def gen_recommendations():
    """Brand-voice-aligned content recommendations per cluster."""
    types = ["Pillar guide", "Comparison page", "How-to guide", "Framework explainer",
             "Examples + templates post", "Benchmark + data report"]
    angles = [
        "data-driven analysis with real benchmarks",
        "step-by-step playbook from teams who've done it",
        "contrarian take backed by survey data",
        "named-example walkthrough with numbers",
        "buyer's-guide format with framework",
        "research-backed depth + diagrams",
    ]
    cta_styles = ["consultative", "demo-led", "research-download", "trial-led", "newsletter signup"]
    rows = []
    for c in CLUSTERS:
        rows.append({
            "cluster_id": c["id"],
            "cluster_name": c["name"],
            "content_type": random.choice(types),
            "tone": "Authoritative + data-driven",
            "angle": random.choice(angles),
            "cta_style": random.choice(cta_styles),
        })
    return rows


def gen_search_intent(url_map):
    rows = []
    types = ["informational", "commercial", "transactional", "navigational"]
    weights = [0.55, 0.25, 0.15, 0.05]
    for u in url_map:
        if u["main_cluster"] == -1:
            continue
        primary = random.choices(types, weights)[0]
        secondary = random.choice([t for t in types if t != primary])
        rows.append({
            "url": u["url"],
            "primary_intent": primary,
            "secondary_intent": secondary,
            "confidence": round(random.uniform(0.55, 0.92), 2),
            "transactional_signals": random.randint(0, 8),
            "commercial_signals": random.randint(0, 12),
            "informational_signals": random.randint(2, 18),
            "navigational_signals": random.randint(0, 4),
        })
    return rows


def gen_content_freshness(url_map):
    rows = []
    today = datetime(2026, 4, 27)
    age_buckets = [
        ("Fresh (< 1 month)", 15, 0.18),
        ("Recent (1-3 months)", 60, 0.22),
        ("Aging (3-6 months)", 120, 0.26),
        ("Stale (6-12 months)", 240, 0.20),
        ("Decaying (12+ months)", 540, 0.14),
    ]
    indexed_urls = [u for u in url_map if u["main_cluster"] != -1][:120]
    for u in indexed_urls:
        bucket = random.choices(age_buckets, [w for _, _, w in age_buckets])[0]
        label, base_age, _ = bucket
        age = base_age + random.randint(-15, 30)
        date = today - timedelta(days=age)
        rows.append({
            "url": u["url"],
            "lastmod": date.strftime("%Y-%m-%d"),
            "age_days": age,
            "freshness": label,
        })
    return rows


def gen_brand_voice_scores(url_map):
    rows = []
    ratings = ["On-brand", "Partially aligned", "Needs work", "Off-brand"]
    rating_weights = [0.32, 0.41, 0.21, 0.06]
    for u in url_map[:140]:
        if u["main_cluster"] == -1:
            continue
        rating = random.choices(ratings, rating_weights)[0]
        score = {"On-brand": random.randint(75, 95),
                 "Partially aligned": random.randint(55, 74),
                 "Needs work": random.randint(35, 54),
                 "Off-brand": random.randint(15, 34)}[rating]
        tones = ["data-driven", "authoritative", "pragmatic", "concise"]
        rows.append({
            "url": u["url"],
            "brand_score": score,
            "tone_alignment": f"{score}%",
            "tone_matches": ", ".join(random.sample(tones, k=random.randint(1, 3))),
            "style_match": random.choice(["Yes", "No"]),
            "avg_sentence_length": round(random.uniform(11, 19), 1),
            "violations": random.choice(["", "fluff words detected", "jargon detected", "passive voice"]),
            "rating": rating,
        })
    rows.sort(key=lambda r: r["brand_score"])
    return rows


def gen_similarity_scores(url_map):
    rows = []
    # Pick 20 same-cluster pairs with high similarity
    by_cluster = {}
    for u in url_map:
        if u["main_cluster"] == -1:
            continue
        by_cluster.setdefault(u["main_cluster"], []).append(u["url"])
    pairs = []
    for cid, urls in by_cluster.items():
        if len(urls) < 2:
            continue
        for i in range(min(3, len(urls) - 1)):
            pairs.append((cid, urls[i], urls[i + 1]))
    pairs = pairs[:25]
    for cid, a, b in pairs:
        sim = round(random.uniform(0.78, 0.96), 4)
        a_type = "service" if "/services/" in a else "case-study" if "/case-study/" in a else "blog"
        b_type = "service" if "/services/" in b else "case-study" if "/case-study/" in b else "blog"
        types = {a_type, b_type}
        money = {"service"}
        info = {"blog"}
        is_conv = bool(types & money) and bool(types & info)
        if is_conv:
            action = "CRITICAL: blog page may outrank service page — cannibalizing conversions"
        elif sim >= 0.92:
            action = "MERGE: near-duplicate content — consolidate into one page"
        elif sim >= 0.80:
            action = "REVIEW: very similar — differentiate angles or merge"
        else:
            action = "DIFFERENTIATE: overlap exists — ensure unique intent per page"
        rows.append({
            "cluster_id": cid,
            "url_a": a,
            "url_b": b,
            "type_a": a_type,
            "type_b": b_type,
            "similarity": sim,
            "conversion_risk": is_conv,
            "action": action,
        })
    rows.sort(key=lambda r: (not r["conversion_risk"], -r["similarity"]))
    return rows


def gen_competitor_clusters(competitor_name):
    """Each competitor has ~25 clusters of their own."""
    base = [
        "Customer Analytics", "Event Tracking SDKs", "Funnel Optimization", "Retention Modeling",
        "Onboarding Playbooks", "Feature Flag Strategy", "Experimentation Platform", "Behavioral Segmentation",
        "Mobile SDK Integration", "GDPR Compliance", "Reverse ETL", "Marketing Attribution",
        "Cohort Analysis", "Customer Journey", "Real-Time Dashboards", "Self-Serve BI",
        "Activation Tactics", "Churn Modeling", "Push Notification Best Practices", "Email Lifecycle",
        "Heatmap Analytics", "Session Replay Tools", "Attribution Modeling", "Product Adoption",
        "Streaming Pipelines",
    ]
    rows = []
    for i, name in enumerate(base):
        rows.append({
            "cluster_id": i,
            "cluster_name": name,
            "keywords": name.lower() + ", " + name.lower().replace(" ", "_") + ", " + name.split()[-1].lower(),
        })
    return rows


def gen_competitor_gap(competitor_name, target_clusters):
    """Generate gap analysis between us and a single competitor."""
    rows = []
    target_topic_set = set()
    for c in target_clusters:
        target_topic_set.add(c["cluster_name"].lower())
        for k in c["keywords"].split(","):
            target_topic_set.add(k.strip().lower())

    comp_clusters = gen_competitor_clusters(competitor_name)
    comp_topic_set = set()
    for c in comp_clusters:
        comp_topic_set.add(c["cluster_name"].lower())
        for k in c["keywords"].split(","):
            comp_topic_set.add(k.strip().lower())

    # GAPS (competitor has, target doesn't) — fictional but plausible analytics topics
    gap_topics = {
        "BeaconAnalytics": [
            "best customer data platform", "tracking plan", "activation rate benchmarks",
            "what is product telemetry", "how to set up funnel analysis",
            "what is marketing attribution", "behavioral segmentation",
            "real-time streaming analytics", "dau mau ratio tracking",
            "in-app surveys", "time-to-value measurement", "customer journey mapping implementation",
            "churn rate benchmarks", "product adoption framework",
        ],
        "PulseGrid": [
            "best customer data platform", "best session replay tools", "jtbd framework",
            "what is pql", "best heatmap tools", "best mobile analytics tools",
            "heatmap analytics", "multi-touch attribution modeling", "reverse etl",
            "onboarding funnel optimization", "funnel drop-off analysis", "product-led seo strategy",
            "push notification strategy", "email engagement tracking setup",
        ],
        "Insightspark": [
            "tracking plan", "jtbd framework", "what is pql",
            "cohort analysis framework", "how to run ab test", "how to build nps tracking",
            "what is self-serve analytics", "voice of customer framework",
            "customer health scoring", "gdpr-compliant analytics",
            "free-to-paid conversion tracking", "conversion rate benchmarks",
        ],
    }
    advantage_topics = ["product narrative", "narrative metrics", "lumenflow signals",
                        "demo experience analytics", "founder dashboards"]
    shared_topics = ["event schema design", "ab testing framework", "customer analytics platform",
                     "product telemetry", "user behavior tracking", "feature adoption",
                     "funnel analysis"]
    for t in gap_topics.get(competitor_name, []):
        rows.append({"keyword": t, "status": "GAP: competitor covers, you don't", "competitor": competitor_name})
    for t in advantage_topics:
        rows.append({"keyword": t, "status": "ADVANTAGE: you cover, competitor doesn't", "competitor": competitor_name})
    for t in shared_topics:
        rows.append({"keyword": t, "status": "SHARED: both cover", "competitor": competitor_name})
    return rows


def gen_cluster_merge_suggestions():
    pairs = [
        (4, 5, 0.86, "MERGE"),
        (16, 17, 0.74, "REVIEW for merge"),
        (3, 28, 0.72, "REVIEW for merge"),
        (10, 1, 0.71, "REVIEW for merge"),
    ]
    return [
        {
            "cluster_a_id": a, "cluster_a_name": CLUSTERS[a]["name"],
            "cluster_b_id": b, "cluster_b_name": CLUSTERS[b]["name"],
            "similarity": sim, "recommendation": rec,
        }
        for a, b, sim, rec in pairs
    ]


def gen_content_ideas():
    rows = []
    for i in CONTENT_IDEAS:
        rows.append({
            "priority": i["priority"],
            "title": i["title"],
            "gap_topic": i["topic"],
            "content_type": i["type"],
            "intent": i["intent"],
            "target_audience": i["audience"],
            "suggested_keywords": i["kws"],
            "key_questions": i["questions"],
            "est_word_count": i["words"],
            "covered_by": i["covered_by"],
            "num_competitors": i["n_comp"],
            "spoke_cluster": i["spoke"],
            "spoke_similarity": i["spoke_sim"],
            "search_volume": "",
            "keyword_difficulty": "",
            "parent_keyword": "",
            "seo_data_source": "none",
        })
    return rows


def gen_brand_profile():
    return {
        "brand_name": SITE_NAME,
        "tone": ["Authoritative", "Data-driven", "Pragmatic", "Concise", "Warm"],
        "writing_style": {"sentence_length": "short", "complexity": "intermediate"},
        "audience": "B2B SaaS product, growth, and analytics leaders making data infrastructure decisions.",
        "do": [
            "Ground claims in benchmarks and named examples",
            "Lead with the business problem before the feature",
            "Show before/after with real numbers",
            "Cite primary sources by name",
            "Keep sentences short and active",
        ],
        "dont": [
            "Use vague hyperbole ('revolutionary', 'game-changing')",
            "Bury the lede behind setup paragraphs",
            "Treat readers like beginners — assume product/analytics literacy",
            "Use passive voice for action items",
        ],
        "example_phrases": [
            "Activation rate is the single most predictive metric for B2B SaaS retention.",
            "Top-quartile teams hit 40%+ activation by week 1; median is 22%.",
        ],
        "content_goals": ["build trust through data", "convert through demonstration", "educate the operator"],
    }


def gen_qa_report():
    return {
        "started_at": datetime.now().timestamp(),
        "checks_run": 9,
        "summary": {"critical": 0, "warn": 1, "info": 0},
        "findings": [
            {"severity": "WARN", "check": "freshness.stale_files",
             "message": "0 output files predate this run", "file": None, "sample": None},
        ],
    }


def gen_site_health(brand_score_avg):
    return {
        "composite": 71,
        "composite_label": "yellow",
        "subscores": {
            "coverage": {"score": 88, "label": "green",
                          "detail": f"{len(CLUSTERS)} clusters across ~{sum(CLUSTER_URL_COUNTS)} URLs"},
            "cannibalization": {"score": 55, "label": "yellow",
                                 "detail": f"{len(CANNIB)} of {len(CLUSTERS)} clusters cannibalized"},
            "freshness": {"score": 64, "label": "yellow",
                           "detail": "32 of 120 pages 6+ months old"},
            "brand": {"score": int(brand_score_avg), "label": "yellow" if brand_score_avg < 75 else "green",
                       "detail": f"avg {int(brand_score_avg)}/100 across 140 pages"},
            "competitive": {"score": 68, "label": "yellow",
                             "detail": "covers 78 of 115 unique topics vs competitors"},
        },
        "deltas": {"composite": 4, "coverage": 2, "cannibalization": 6, "freshness": -1, "brand": 0, "competitive": 3},
        "sparkline": [56, 61, 64, 67, 71],
        "site_name": SITE_NAME,
        "site_domain": SITE_DOMAIN,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"→ Generating demo dataset for fictional brand: {SITE_NAME} ({SITE_DOMAIN})")
    if os.path.exists(DEMO_OUTPUT):
        shutil.rmtree(DEMO_OUTPUT)
    if os.path.exists(DEMO_CACHE):
        shutil.rmtree(DEMO_CACHE)
    os.makedirs(DEMO_OUTPUT, exist_ok=True)
    os.makedirs(DEMO_CACHE, exist_ok=True)

    # --- Site config + cache ---
    from src.config import SiteConfig, save_site_config, set_runtime_cache_dir
    set_runtime_cache_dir(DEMO_CACHE)
    cfg = SiteConfig(
        name=SITE_NAME, domain=SITE_DOMAIN, industry=SITE_INDUSTRY,
        sitemaps=[f"https://{SITE_DOMAIN}/sitemap.xml"],
        competitors=COMPETITORS,
        output_dir=DEMO_OUTPUT,
    )
    save_site_config(cfg)
    with open(os.path.join(DEMO_CACHE, "brand_profile.json"), "w") as f:
        json.dump(gen_brand_profile(), f, indent=2)

    # --- Generate all CSVs ---
    clusters = gen_clusters()
    write_csv(f"{DEMO_OUTPUT}/clusters.csv", clusters)
    print(f"  • clusters.csv ({len(clusters)} clusters)")

    url_map = gen_url_mapping()
    write_csv(f"{DEMO_OUTPUT}/url_mapping.csv", url_map)
    print(f"  • url_mapping.csv ({len(url_map)} URLs)")

    cannib = gen_cannibalization(url_map)
    write_csv(f"{DEMO_OUTPUT}/cannibalization.csv", cannib)
    print(f"  • cannibalization.csv ({len(cannib)} clusters)")

    skipped = gen_skipped_urls()
    write_csv(f"{DEMO_OUTPUT}/skipped_urls.csv", skipped, columns=["url", "reason"])
    print(f"  • skipped_urls.csv ({len(skipped)} pages)")

    recs = gen_recommendations()
    write_csv(f"{DEMO_OUTPUT}/recommendations.csv", recs)

    intent = gen_search_intent(url_map)
    write_csv(f"{DEMO_OUTPUT}/search_intent.csv", intent)
    print(f"  • search_intent.csv ({len(intent)} URLs)")

    fresh = gen_content_freshness(url_map)
    write_csv(f"{DEMO_OUTPUT}/content_freshness.csv", fresh)
    print(f"  • content_freshness.csv ({len(fresh)} URLs)")

    brand = gen_brand_voice_scores(url_map)
    write_csv(f"{DEMO_OUTPUT}/brand_voice_scores.csv", brand)
    print(f"  • brand_voice_scores.csv ({len(brand)} URLs)")
    avg_brand = sum(b["brand_score"] for b in brand) / max(len(brand), 1)

    sim = gen_similarity_scores(url_map)
    write_csv(f"{DEMO_OUTPUT}/similarity_scores.csv", sim)

    merges = gen_cluster_merge_suggestions()
    write_csv(f"{DEMO_OUTPUT}/cluster_merge_suggestions.csv", merges)

    for comp in COMPETITORS:
        cc = gen_competitor_clusters(comp)
        write_csv(f"{DEMO_OUTPUT}/competitor_{comp.lower()}_clusters.csv", cc)
        gap = gen_competitor_gap(comp, clusters)
        write_csv(f"{DEMO_OUTPUT}/competitor_gap_{comp.lower()}.csv", gap)
    print(f"  • {len(COMPETITORS)} competitor cluster + gap CSVs")

    ideas = gen_content_ideas()
    write_csv(f"{DEMO_OUTPUT}/content_ideas.csv", ideas)
    print(f"  • content_ideas.csv ({len(ideas)} briefs)")

    with open(f"{DEMO_OUTPUT}/site_health.json", "w") as f:
        json.dump(gen_site_health(avg_brand), f, indent=2)
    with open(f"{DEMO_OUTPUT}/qa_report.json", "w") as f:
        json.dump(gen_qa_report(), f, indent=2)

    # --- Render dashboard / exec summary / artifact ---
    print("→ Rendering dashboard...")
    from src.dashboard import generate_dashboard
    generate_dashboard(site_config=cfg)

    print("→ Rendering exec summary...")
    from src.exec_summary import generate_exec_summary
    generate_exec_summary(site_config=cfg)

    print("→ Rendering Claude artifact...")
    from src.dashboard_artifact import generate_artifact
    generate_artifact(site_config=cfg)

    print()
    print("=" * 60)
    print("DEMO DATASET READY")
    print("=" * 60)
    print(f"  Dashboard:    file://{DEMO_OUTPUT}/dashboard.html")
    print(f"  Exec summary: file://{DEMO_OUTPUT}/exec_summary.html")
    print(f"  Artifact:     {DEMO_OUTPUT}/dashboard_artifact.tsx")
    print()
    print("To open locally:")
    print(f"  open {DEMO_OUTPUT}/dashboard.html")


if __name__ == "__main__":
    main()
