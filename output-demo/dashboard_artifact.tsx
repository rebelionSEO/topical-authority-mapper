import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
  ZAxis,
  ReferenceLine,
} from "recharts";

const DATA = {
  "site": {
    "name": "Lumenflow",
    "domain": "lumenflow.demo",
    "industry": "b2b-saas"
  },
  "stats": {
    "urls": 198,
    "clusters": 30,
    "cannib": 8,
    "ideas": 38,
    "p1_ideas": 5
  },
  "health": {
    "composite": 71,
    "composite_label": "yellow",
    "subscores": {
      "coverage": {
        "score": 88,
        "label": "green",
        "detail": "30 clusters across ~190 URLs"
      },
      "cannibalization": {
        "score": 55,
        "label": "yellow",
        "detail": "8 of 30 clusters cannibalized"
      },
      "freshness": {
        "score": 64,
        "label": "yellow",
        "detail": "32 of 120 pages 6+ months old"
      },
      "brand": {
        "score": 65,
        "label": "yellow",
        "detail": "avg 65/100 across 140 pages"
      },
      "competitive": {
        "score": 68,
        "label": "yellow",
        "detail": "covers 78 of 115 unique topics vs competitors"
      }
    },
    "deltas": {
      "composite": 4,
      "coverage": 2,
      "cannibalization": 6,
      "freshness": -1,
      "brand": 0,
      "competitive": 3
    },
    "sparkline": [
      56,
      61,
      64,
      67,
      71
    ],
    "site_name": "Lumenflow",
    "site_domain": "lumenflow.demo"
  },
  "clusters": [
    {
      "id": 0,
      "name": "Customer Analytics Platform",
      "urls": 12,
      "keywords": "customer analytics, behavioral data, user insights, analytics platform, customer intelligence, data-",
      "cannibalized": true
    },
    {
      "id": 2,
      "name": "User Behavior Tracking",
      "urls": 11,
      "keywords": "user behavior, behavior tracking, click tracking, user journey, behavior analytics, session tracking",
      "cannibalized": true
    },
    {
      "id": 9,
      "name": "A/B Testing Framework",
      "urls": 10,
      "keywords": "ab testing, experiment design, split testing, statistical significance, hypothesis testing, conversi",
      "cannibalized": true
    },
    {
      "id": 20,
      "name": "Product-Led Growth",
      "urls": 9,
      "keywords": "product led growth, plg, plg metrics, product qualified leads, pql, free to paid conversion",
      "cannibalized": false
    },
    {
      "id": 5,
      "name": "Retention Metrics",
      "urls": 9,
      "keywords": "retention metrics, user retention, customer retention, retention curves, dau mau ratio, repeat usage",
      "cannibalized": true
    },
    {
      "id": 28,
      "name": "Conversion Optimization",
      "urls": 8,
      "keywords": "conversion rate optimization, cro, conversion analytics, landing page optimization, conversion testi",
      "cannibalized": true
    },
    {
      "id": 1,
      "name": "Product Telemetry",
      "urls": 8,
      "keywords": "product telemetry, event tracking, telemetry data, instrumentation, sdk integration, event schema",
      "cannibalized": false
    },
    {
      "id": 14,
      "name": "Dashboard Building",
      "urls": 8,
      "keywords": "dashboard building, kpi dashboard, custom dashboards, data visualization, executive dashboards, dash",
      "cannibalized": true
    },
    {
      "id": 19,
      "name": "Marketing Attribution",
      "urls": 7,
      "keywords": "marketing attribution, multi-touch attribution, attribution modeling, channel attribution, mta, attr",
      "cannibalized": false
    },
    {
      "id": 15,
      "name": "Self-Serve Analytics",
      "urls": 7,
      "keywords": "self-serve analytics, no-code analytics, self-service bi, ad-hoc analysis, citizen data analyst, dem",
      "cannibalized": false
    },
    {
      "id": 7,
      "name": "Feature Adoption",
      "urls": 7,
      "keywords": "feature adoption, feature usage, adoption rate, feature analytics, power users, sticky features",
      "cannibalized": true
    },
    {
      "id": 3,
      "name": "Funnel Analysis",
      "urls": 7,
      "keywords": "funnel analysis, conversion funnel, drop-off rates, funnel optimization, multi-step funnel, funnel v",
      "cannibalized": true
    },
    {
      "id": 10,
      "name": "Event Schema Design",
      "urls": 6,
      "keywords": "event schema, event taxonomy, event naming, tracking plan, schema design, event properties",
      "cannibalized": false
    },
    {
      "id": 17,
      "name": "Web Analytics",
      "urls": 6,
      "keywords": "web analytics, website tracking, page analytics, traffic analytics, web events, browser events",
      "cannibalized": false
    },
    {
      "id": 4,
      "name": "Cohort Reporting",
      "urls": 6,
      "keywords": "cohort analysis, cohort reporting, retention cohorts, cohort metrics, behavioral cohorts, time-based",
      "cannibalized": false
    },
    {
      "id": 13,
      "name": "Data Pipeline Architecture",
      "urls": 6,
      "keywords": "data pipeline, etl pipeline, real-time pipeline, data ingestion, streaming analytics, pipeline archi",
      "cannibalized": false
    },
    {
      "id": 29,
      "name": "SaaS Metrics",
      "urls": 6,
      "keywords": "saas metrics, mrr, arr, cac, ltv, expansion revenue, net revenue retention",
      "cannibalized": false
    },
    {
      "id": 16,
      "name": "Mobile App Analytics",
      "urls": 5,
      "keywords": "mobile analytics, app analytics, ios analytics, android tracking, mobile sdk, app engagement",
      "cannibalized": false
    },
    {
      "id": 6,
      "name": "Onboarding Optimization",
      "urls": 5,
      "keywords": "onboarding flow, user onboarding, activation metrics, onboarding optimization, time to value, first ",
      "cannibalized": false
    },
    {
      "id": 11,
      "name": "Session Replay",
      "urls": 5,
      "keywords": "session replay, session recording, user session playback, screen recording, behavioral replay, ux de",
      "cannibalized": false
    },
    {
      "id": 21,
      "name": "Customer Journey Mapping",
      "urls": 5,
      "keywords": "customer journey, journey mapping, journey analytics, lifecycle stages, customer touchpoints, journe",
      "cannibalized": false
    },
    {
      "id": 24,
      "name": "Heatmaps",
      "urls": 5,
      "keywords": "heatmaps, click heatmaps, scroll maps, attention maps, heatmap analytics, ui hotspots",
      "cannibalized": false
    },
    {
      "id": 27,
      "name": "Email Engagement",
      "urls": 5,
      "keywords": "email engagement, email analytics, open rates, click rates, lifecycle emails, behavioral email",
      "cannibalized": false
    },
    {
      "id": 8,
      "name": "Churn Prediction",
      "urls": 4,
      "keywords": "churn prediction, churn analysis, predictive churn, churn risk, retention modeling, customer health ",
      "cannibalized": false
    },
    {
      "id": 18,
      "name": "E-commerce Tracking",
      "urls": 4,
      "keywords": "ecommerce tracking, purchase events, cart analytics, checkout funnel, ecommerce metrics, transaction",
      "cannibalized": false
    },
    {
      "id": 22,
      "name": "Voice of Customer",
      "urls": 4,
      "keywords": "voice of customer, voc, customer feedback, in-app surveys, nps surveys, customer sentiment",
      "cannibalized": false
    },
    {
      "id": 23,
      "name": "NPS Tracking",
      "urls": 4,
      "keywords": "nps tracking, net promoter score, nps surveys, promoter detractor, nps benchmarks, customer loyalty",
      "cannibalized": false
    },
    {
      "id": 25,
      "name": "Personalization Engine",
      "urls": 4,
      "keywords": "personalization, dynamic content, behavioral personalization, recommendation engine, ai personalizat",
      "cannibalized": false
    },
    {
      "id": 12,
      "name": "Privacy Compliance",
      "urls": 4,
      "keywords": "privacy compliance, gdpr analytics, ccpa, data anonymization, consent management, privacy by design",
      "cannibalized": false
    },
    {
      "id": 26,
      "name": "Push Notification Strategy",
      "urls": 3,
      "keywords": "push notifications, push strategy, mobile push, push automation, notification timing, push engagemen",
      "cannibalized": false
    }
  ],
  "cannib": [
    {
      "id": 0,
      "name": "Customer Analytics Platform",
      "count": 12,
      "severity": "critical",
      "urls": [
        "/post/customer-analytics-platform-tutorial-1",
        "/blog/customer-analytics-platform-best-practices",
        "/guide/customer-analytics-platform-explained",
        "/post/how-to-customer-analytics-platform-4",
        "/case-study/customer-analytics-platform-umbrella"
      ],
      "more": 7
    },
    {
      "id": 2,
      "name": "User Behavior Tracking",
      "count": 11,
      "severity": "critical",
      "urls": [
        "/post/user-behavior-tracking-tutorial-1",
        "/blog/user-behavior-tracking-best-practices",
        "/guide/user-behavior-tracking-explained",
        "/post/how-to-user-behavior-tracking-4",
        "/case-study/user-behavior-tracking-umbrella"
      ],
      "more": 6
    },
    {
      "id": 9,
      "name": "A/B Testing Framework",
      "count": 10,
      "severity": "critical",
      "urls": [
        "/post/a-b-testing-framework-tutorial-1",
        "/blog/a-b-testing-framework-best-practices",
        "/guide/a-b-testing-framework-explained",
        "/post/how-to-a-b-testing-framework-4",
        "/case-study/a-b-testing-framework-umbrella"
      ],
      "more": 5
    },
    {
      "id": 5,
      "name": "Retention Metrics",
      "count": 9,
      "severity": "high",
      "urls": [
        "/post/retention-metrics-tutorial-1",
        "/blog/retention-metrics-best-practices",
        "/guide/retention-metrics-explained",
        "/post/how-to-retention-metrics-4",
        "/case-study/retention-metrics-umbrella"
      ],
      "more": 4
    },
    {
      "id": 14,
      "name": "Dashboard Building",
      "count": 8,
      "severity": "high",
      "urls": [
        "/post/dashboard-building-tutorial-1",
        "/blog/dashboard-building-best-practices",
        "/guide/dashboard-building-explained",
        "/post/how-to-dashboard-building-4",
        "/case-study/dashboard-building-umbrella"
      ],
      "more": 3
    },
    {
      "id": 28,
      "name": "Conversion Optimization",
      "count": 8,
      "severity": "high",
      "urls": [
        "/post/conversion-optimization-tutorial-1",
        "/blog/conversion-optimization-best-practices",
        "/guide/conversion-optimization-explained",
        "/post/how-to-conversion-optimization-4",
        "/case-study/conversion-optimization-umbrella"
      ],
      "more": 3
    },
    {
      "id": 3,
      "name": "Funnel Analysis",
      "count": 7,
      "severity": "high",
      "urls": [
        "/post/funnel-analysis-tutorial-1",
        "/blog/funnel-analysis-best-practices",
        "/guide/funnel-analysis-explained",
        "/post/how-to-funnel-analysis-4",
        "/case-study/funnel-analysis-umbrella"
      ],
      "more": 2
    },
    {
      "id": 7,
      "name": "Feature Adoption",
      "count": 7,
      "severity": "high",
      "urls": [
        "/post/feature-adoption-tutorial-1",
        "/blog/feature-adoption-best-practices",
        "/guide/feature-adoption-explained",
        "/post/how-to-feature-adoption-4",
        "/case-study/feature-adoption-umbrella"
      ],
      "more": 2
    }
  ],
  "ideas": [
    {
      "priority": "P1",
      "title": "Best Customer Data Platform: A B2B SaaS Product Marketing Buyer's Guide",
      "topic": "best customer data platform",
      "type": "Comparison page",
      "intent": "comparison",
      "audience": "Product marketing + RevOps teams",
      "words": 2500,
      "covered_by": "BeaconAnalytics, PulseGrid",
      "keywords": [
        "best customer data platform",
        "customer data platform alternatives",
        "top customer data platforms"
      ],
      "questions": [
        "Who are the top alternatives for customer data platform?",
        "How do they differ on pricing, integrations, ideal use case?",
        "Which option fits B2B SaaS teams of different sizes?",
        "What's the strongest case for picking the runner-up over the leader?",
        "What concise definition would an LLM cite for 'customer data platform'?",
        "What 6-10 People-Also-Ask questions does Google currently surface?",
        "What schema.org markup is appropriate (FAQPage, Product)?",
        "Which 3-5 authoritative sources should you cite?",
        "What internal pages should you link from + to?"
      ]
    },
    {
      "priority": "P1",
      "title": "How to Build a Tracking Plan: A Practical Guide for Product + Engineering Teams",
      "topic": "tracking plan",
      "type": "How-to guide",
      "intent": "howto",
      "audience": "Product + engineering teams",
      "words": 1800,
      "covered_by": "BeaconAnalytics, Insightspark",
      "keywords": [
        "tracking plan",
        "how to build a tracking plan",
        "tracking plan template"
      ],
      "questions": [
        "What's the step-by-step process for building a tracking plan?",
        "What are common mistakes to avoid?",
        "What templates and tools cut the time in half?",
        "What does 'before vs after' look like with real numbers?",
        "What concise definition for 'tracking plan' would an LLM cite?",
        "What People-Also-Ask questions does Google surface?",
        "What schema.org markup applies (HowTo, Article)?",
        "Which authoritative sources should you cite?",
        "What internal pages link from + to?"
      ]
    },
    {
      "priority": "P1",
      "title": "The JTBD Framework: How Product Teams Use It for Activation",
      "topic": "jtbd framework",
      "type": "Framework explainer",
      "intent": "framework",
      "audience": "Product + UX research teams",
      "words": 1500,
      "covered_by": "PulseGrid, Insightspark",
      "keywords": [
        "jtbd framework",
        "jobs to be done framework",
        "jtbd model"
      ],
      "questions": [
        "What is the JTBD framework, who originated it, and what problem does it solve?",
        "When should a team apply it? When should they avoid it?",
        "What are the steps + outputs at each stage?",
        "What does a worked example look like end-to-end?",
        "What concise definition for 'jtbd framework' would an LLM cite?",
        "What PAA questions does Google surface?",
        "What schema.org markup applies?",
        "Which authoritative sources to cite?",
        "What internal pages link from + to?"
      ]
    },
    {
      "priority": "P1",
      "title": "Activation Rate Benchmarks: What B2B SaaS Product Teams Should Be Hitting",
      "topic": "activation rate benchmarks",
      "type": "Benchmark + data report",
      "intent": "metrics",
      "audience": "Product-led growth teams",
      "words": 1400,
      "covered_by": "BeaconAnalytics, PulseGrid",
      "keywords": [
        "activation rate benchmarks",
        "average activation rate",
        "b2b saas activation benchmark"
      ],
      "questions": [
        "What are the current benchmarks for activation rate?",
        "How do top-quartile teams compare to median?",
        "How does this benchmark vary by company size, industry, GTM motion?",
        "What's the right cadence to measure and recalibrate?",
        "What concise definition would an LLM cite?",
        "What PAA questions does Google surface?",
        "What schema.org applies?",
        "Which sources to cite?",
        "What internal pages to link?"
      ]
    },
    {
      "priority": "P1",
      "title": "What Is Product-Qualified Lead (PQL)? A Complete Guide for PLG Teams",
      "topic": "what is pql",
      "type": "Pillar / definitive guide",
      "intent": "definition",
      "audience": "Product-led growth teams",
      "words": 2000,
      "covered_by": "PulseGrid, BeaconAnalytics",
      "keywords": [
        "what is pql",
        "product qualified lead",
        "pql definition"
      ],
      "questions": [
        "What does 'PQL' actually mean (and what isn't it)?",
        "Why does it matter for PLG teams right now?",
        "How do leading teams use it in practice \u2014 with one named example?",
        "What's the most common misconception worth correcting upfront?",
        "What concise LLM-citable definition?",
        "What PAA questions does Google surface?",
        "What schema.org?",
        "Which sources to cite?",
        "What internal pages?"
      ]
    },
    {
      "priority": "P2",
      "title": "How to Set Up Funnel Analysis: A Practical Guide for Product Marketing + Content Teams",
      "topic": "funnel analysis setup",
      "type": "How-to guide",
      "intent": "howto",
      "audience": "Product marketing + content teams",
      "words": 1800,
      "covered_by": "BeaconAnalytics",
      "keywords": [
        "funnel analysis setup",
        "how to set up funnel",
        "conversion funnel tutorial"
      ],
      "questions": [
        "What's the step-by-step process?",
        "Common mistakes to avoid?",
        "Templates and tools that help?",
        "Before/after numbers?",
        "LLM-citable definition?",
        "PAA questions?",
        "Schema.org?",
        "Sources to cite?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "The Cohort Analysis Framework: How Product Teams Use It",
      "topic": "cohort analysis framework",
      "type": "Framework explainer",
      "intent": "framework",
      "audience": "Product + UX research teams",
      "words": 1500,
      "covered_by": "Insightspark",
      "keywords": [
        "cohort analysis framework",
        "cohort framework",
        "cohort model"
      ],
      "questions": [
        "What is the cohort framework?",
        "When to apply / avoid?",
        "Steps + outputs at each stage?",
        "Worked example?",
        "LLM definition?",
        "PAA questions?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "Best Session Replay Tools: A B2B SaaS Buyer's Guide",
      "topic": "best session replay tools",
      "type": "Comparison page",
      "intent": "comparison",
      "audience": "Product marketing + content teams",
      "words": 2500,
      "covered_by": "PulseGrid",
      "keywords": [
        "best session replay tools",
        "session replay alternatives",
        "top session replay"
      ],
      "questions": [
        "Top alternatives?",
        "How do they differ on pricing/features/use case?",
        "Which fits SMB / mid-market / enterprise?",
        "Strongest case for the runner-up?",
        "LLM-citable summary?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "Churn Rate Benchmarks: What SaaS Product Teams Should Be Hitting",
      "topic": "churn rate benchmarks",
      "type": "Benchmark + data report",
      "intent": "metrics",
      "audience": "Customer success + retention teams",
      "words": 1400,
      "covered_by": "BeaconAnalytics",
      "keywords": [
        "churn rate benchmarks",
        "average churn rate",
        "b2b saas churn benchmark"
      ],
      "questions": [
        "Current benchmarks (top-quartile, median, bottom)?",
        "What drives the gap?",
        "Variation by size/industry/motion?",
        "Right cadence to measure?",
        "LLM definition?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "How to Run an A/B Test: A Practical Guide for Growth + Product Teams",
      "topic": "how to run ab test",
      "type": "How-to guide",
      "intent": "howto",
      "audience": "Growth + product teams",
      "words": 1800,
      "covered_by": "Insightspark",
      "keywords": [
        "how to run ab test",
        "ab testing tutorial",
        "split testing guide"
      ],
      "questions": [
        "Step-by-step?",
        "Mistakes to avoid?",
        "Templates?",
        "Before/after?",
        "LLM definition?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "What Is Product Telemetry? A Complete Guide for Product + Engineering Teams",
      "topic": "what is product telemetry",
      "type": "Pillar / definitive guide",
      "intent": "definition",
      "audience": "Product + engineering teams",
      "words": 2000,
      "covered_by": "BeaconAnalytics",
      "keywords": [
        "what is product telemetry",
        "product telemetry definition",
        "telemetry for products"
      ],
      "questions": [
        "What does it mean (and what isn't it)?",
        "Why does it matter now?",
        "How do leading teams use it?",
        "Common misconception?",
        "LLM definition?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "Best Heatmap Tools: A Conversion Optimization Buyer's Guide",
      "topic": "best heatmap tools",
      "type": "Comparison page",
      "intent": "comparison",
      "audience": "Analytics + growth teams",
      "words": 2500,
      "covered_by": "PulseGrid",
      "keywords": [
        "best heatmap tools",
        "heatmap alternatives",
        "top heatmap software"
      ],
      "questions": [
        "Top alternatives?",
        "How do they differ?",
        "Best fit by size?",
        "Runner-up case?",
        "LLM summary?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "How to Build an NPS Tracking Program: A Practical Guide for Customer Success + Retention Teams",
      "topic": "how to build nps tracking",
      "type": "How-to guide",
      "intent": "howto",
      "audience": "Customer success + retention teams",
      "words": 1800,
      "covered_by": "Insightspark",
      "keywords": [
        "how to build nps tracking",
        "nps tracking program",
        "nps survey setup"
      ],
      "questions": [
        "Step-by-step?",
        "Mistakes?",
        "Templates?",
        "Before/after?",
        "LLM def?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "What Is Marketing Attribution? A Complete Guide for Marketing + Growth Teams",
      "topic": "what is marketing attribution",
      "type": "Pillar / definitive guide",
      "intent": "definition",
      "audience": "Marketing + growth teams",
      "words": 2000,
      "covered_by": "BeaconAnalytics",
      "keywords": [
        "what is marketing attribution",
        "marketing attribution definition",
        "attribution explained"
      ],
      "questions": [
        "What does it mean?",
        "Why does it matter?",
        "How do leading teams use it?",
        "Misconception?",
        "LLM def?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "The Product Adoption Framework: How SaaS Product Teams Use It",
      "topic": "product adoption framework",
      "type": "Framework explainer",
      "intent": "framework",
      "audience": "Product-led growth teams",
      "words": 1500,
      "covered_by": "PulseGrid",
      "keywords": [
        "product adoption framework",
        "adoption framework",
        "feature adoption model"
      ],
      "questions": [
        "What is the framework?",
        "When to apply/avoid?",
        "Steps + outputs?",
        "Worked example?",
        "LLM def?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "Conversion Rate Benchmarks: What Growth Teams Should Be Hitting",
      "topic": "conversion rate benchmarks",
      "type": "Benchmark + data report",
      "intent": "metrics",
      "audience": "Growth + product teams",
      "words": 1400,
      "covered_by": "Insightspark",
      "keywords": [
        "conversion rate benchmarks",
        "average conversion rate",
        "b2b saas conversion benchmark"
      ],
      "questions": [
        "Current benchmarks?",
        "Top-quartile vs median?",
        "Variation by size/industry?",
        "Cadence?",
        "LLM def?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "How to Implement Customer Journey Mapping: A Practical Guide",
      "topic": "customer journey mapping implementation",
      "type": "How-to guide",
      "intent": "howto",
      "audience": "Product + UX research teams",
      "words": 1800,
      "covered_by": "BeaconAnalytics",
      "keywords": [
        "customer journey mapping implementation",
        "implement customer journey",
        "journey mapping setup"
      ],
      "questions": [
        "Step-by-step?",
        "Mistakes?",
        "Templates?",
        "Before/after?",
        "LLM def?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "Best Mobile Analytics Tools: A B2B SaaS Buyer's Guide",
      "topic": "best mobile analytics tools",
      "type": "Comparison page",
      "intent": "comparison",
      "audience": "Mobile product + growth teams",
      "words": 2500,
      "covered_by": "PulseGrid",
      "keywords": [
        "best mobile analytics tools",
        "mobile analytics alternatives",
        "top mobile analytics"
      ],
      "questions": [
        "Top alternatives?",
        "How do they differ?",
        "Best fit by size?",
        "Runner-up case?",
        "LLM summary?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "What Is Self-Serve Analytics? A Complete Guide for Data + Operations Teams",
      "topic": "what is self-serve analytics",
      "type": "Pillar / definitive guide",
      "intent": "definition",
      "audience": "Data + analytics ops teams",
      "words": 2000,
      "covered_by": "Insightspark",
      "keywords": [
        "what is self-serve analytics",
        "self-serve analytics definition",
        "self-service bi explained"
      ],
      "questions": [
        "What does it mean?",
        "Why does it matter?",
        "Leading teams' usage?",
        "Misconception?",
        "LLM def?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "The Voice of Customer Framework: How Product Teams Use It",
      "topic": "voice of customer framework",
      "type": "Framework explainer",
      "intent": "framework",
      "audience": "Product marketing + content teams",
      "words": 1500,
      "covered_by": "BeaconAnalytics",
      "keywords": [
        "voice of customer framework",
        "voc framework",
        "voc model"
      ],
      "questions": [
        "What's the framework?",
        "When to apply/avoid?",
        "Steps + outputs?",
        "Worked example?",
        "LLM def?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P2",
      "title": "How to Set Up Email Engagement Tracking: A Practical Guide for Lifecycle Teams",
      "topic": "email engagement tracking setup",
      "type": "How-to guide",
      "intent": "howto",
      "audience": "Lifecycle marketing teams",
      "words": 1800,
      "covered_by": "PulseGrid",
      "keywords": [
        "email engagement tracking setup",
        "email tracking guide",
        "email analytics setup"
      ],
      "questions": [
        "Step-by-step?",
        "Mistakes?",
        "Templates?",
        "Before/after?",
        "LLM def?",
        "PAA?",
        "Schema.org?",
        "Sources?",
        "Internal links?"
      ]
    },
    {
      "priority": "P3",
      "title": "The Complete Guide to Push Notification Strategy for Mobile Product Teams",
      "topic": "push notification strategy",
      "type": "Pillar guide",
      "intent": "guide",
      "audience": "Mobile product + growth teams",
      "words": 1500,
      "covered_by": "BeaconAnalytics",
      "keywords": [
        "push notification strategy"
      ],
      "questions": [
        "What is it?",
        "Why does it matter?",
        "Common approaches?",
        "Best-in-class?",
        "Failure mode?"
      ]
    },
    {
      "priority": "P3",
      "title": "The Complete Guide to Heatmap Analytics for Conversion Optimization Teams",
      "topic": "heatmap analytics",
      "type": "Pillar guide",
      "intent": "guide",
      "audience": "Analytics + growth teams",
      "words": 1500,
      "covered_by": "PulseGrid",
      "keywords": [
        "heatmap analytics"
      ],
      "questions": [
        "What?",
        "Why?",
        "Approaches?",
        "Best-in-class?",
        "Failure mode?"
      ]
    },
    {
      "priority": "P3",
      "title": "The Complete Guide to Cohort Reporting for Product Teams",
      "topic": "cohort reporting",
      "type": "Pillar guide",
      "intent": "guide",
      "audience": "Product + UX research teams",
      "words": 1500,
      "covered_by": "Insightspark",
      "keywords": [
        "cohort reporting"
      ],
      "questions": [
        "What?",
        "Why?",
        "Approaches?",
        "Best-in-class?",
        "Failure mode?"
      ]
    },
    {
      "priority": "P3",
      "title": "The Complete Guide to Behavioral Segmentation",
      "topic": "behavioral segmentation",
      "type": "Pillar guide",
      "intent": "guide",
      "audience": "Marketing + growth teams",
      "words": 1500,
      "covered_by": "BeaconAnalytics",
      "keywords": [
        "behavioral segmentation"
      ],
      "questions": [
        "What?",
        "Why?",
        "Approaches?",
        "Best-in-class?",
        "Failure mode?"
      ]
    },
    {
      "priority": "P3",
      "title": "The Complete Guide to Multi-Touch Attribution Modeling",
      "topic": "multi-touch attribution modeling",
      "type": "Pillar guide",
      "intent": "guide",
      "audience": "Marketing + growth teams",
      "words": 1500,
      "covered_by": "PulseGrid",
      "keywords": [
        "multi-touch attribution modeling"
      ],
      "questions": [
        "What?",
        "Why?",
        "Approaches?",
        "Best-in-class?",
        "Failure mode?"
      ]
    },
    {
      "priority": "P3",
      "title": "The Complete Guide to Customer Health Scoring",
      "topic": "customer health scoring",
      "type": "Pillar guide",
      "intent": "guide",
      "audience": "Customer success + retention teams",
      "words": 1500,
      "covered_by": "Insightspark",
      "keywords": [
        "customer health scoring"
      ],
      "questions": [
        "What?",
        "Why?",
        "Approaches?",
        "Best-in-class?",
        "Failure mode?"
      ]
    },
    {
      "priority": "P3",
      "title": "The Complete Guide to Real-Time Streaming Analytics",
      "topic": "real-time streaming analytics",
      "type": "Pillar guide",
      "intent": "guide",
      "audience": "Data + analytics ops teams",
      "words": 1500,
      "covered_by": "BeaconAnalytics",
      "keywords": [
        "real-time streaming analytics"
      ],
      "questions": [
        "What?",
        "Why?",
        "Approaches?",
        "Best-in-class?",
        "Failure mode?"
      ]
    },
    {
      "priority": "P3",
      "title": "The Complete Guide to Reverse ETL",
      "topic": "reverse etl",
      "type": "Pillar guide",
      "intent": "guide",
      "audience": "Data + analytics ops teams",
      "words": 1500,
      "covered_by": "PulseGrid",
      "keywords": [
        "reverse etl"
      ],
      "questions": [
        "What?",
        "Why?",
        "Approaches?",
        "Best-in-class?",
        "Failure mode?"
      ]
    },
    {
      "priority": "P3",
      "title": "The Complete Guide to Activation Metrics for SaaS Teams",
      "topic": "activation metrics",
      "type": "Pillar guide",
      "intent": "guide",
      "audience": "Product-led growth teams",
      "words": 1500,
      "covered_by": "Insightspark",
      "keywords": [
        "activation metrics"
      ],
      "questions": [
        "What?",
        "Why?",
        "Approaches?",
        "Best-in-class?",
        "Failure mode?"
      ]
    }
  ],
  "competitors": {
    "names": [
      "Beaconanalytics",
      "Insightspark",
      "Pulsegrid"
    ],
    "rows": [
      {
        "topic": "best customer data platform",
        "target": false,
        "competitors": {
          "Beaconanalytics": true,
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "tracking plan",
        "target": false,
        "competitors": {
          "Beaconanalytics": true,
          "Insightspark": true
        },
        "status": "GAP"
      },
      {
        "topic": "activation rate benchmarks",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "what is product telemetry",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "how to set up funnel analysis",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "what is marketing attribution",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "behavioral segmentation",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "real-time streaming analytics",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "dau mau ratio tracking",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "in-app surveys",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "time-to-value measurement",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "customer journey mapping implementation",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "churn rate benchmarks",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "product adoption framework",
        "target": false,
        "competitors": {
          "Beaconanalytics": true
        },
        "status": "GAP"
      },
      {
        "topic": "product narrative",
        "target": true,
        "competitors": {},
        "status": "ADVANTAGE"
      },
      {
        "topic": "narrative metrics",
        "target": true,
        "competitors": {},
        "status": "ADVANTAGE"
      },
      {
        "topic": "lumenflow signals",
        "target": true,
        "competitors": {},
        "status": "ADVANTAGE"
      },
      {
        "topic": "demo experience analytics",
        "target": true,
        "competitors": {},
        "status": "ADVANTAGE"
      },
      {
        "topic": "founder dashboards",
        "target": true,
        "competitors": {},
        "status": "ADVANTAGE"
      },
      {
        "topic": "event schema design",
        "target": true,
        "competitors": {
          "Beaconanalytics": true,
          "Insightspark": true,
          "Pulsegrid": true
        },
        "status": "SHARED"
      },
      {
        "topic": "ab testing framework",
        "target": true,
        "competitors": {
          "Beaconanalytics": true,
          "Insightspark": true,
          "Pulsegrid": true
        },
        "status": "SHARED"
      },
      {
        "topic": "customer analytics platform",
        "target": true,
        "competitors": {
          "Beaconanalytics": true,
          "Insightspark": true,
          "Pulsegrid": true
        },
        "status": "SHARED"
      },
      {
        "topic": "product telemetry",
        "target": true,
        "competitors": {
          "Beaconanalytics": true,
          "Insightspark": true,
          "Pulsegrid": true
        },
        "status": "SHARED"
      },
      {
        "topic": "user behavior tracking",
        "target": true,
        "competitors": {
          "Beaconanalytics": true,
          "Insightspark": true,
          "Pulsegrid": true
        },
        "status": "SHARED"
      },
      {
        "topic": "feature adoption",
        "target": true,
        "competitors": {
          "Beaconanalytics": true,
          "Insightspark": true,
          "Pulsegrid": true
        },
        "status": "SHARED"
      },
      {
        "topic": "funnel analysis",
        "target": true,
        "competitors": {
          "Beaconanalytics": true,
          "Insightspark": true,
          "Pulsegrid": true
        },
        "status": "SHARED"
      },
      {
        "topic": "jtbd framework",
        "target": false,
        "competitors": {
          "Insightspark": true,
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "what is pql",
        "target": false,
        "competitors": {
          "Insightspark": true,
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "cohort analysis framework",
        "target": false,
        "competitors": {
          "Insightspark": true
        },
        "status": "GAP"
      },
      {
        "topic": "how to run ab test",
        "target": false,
        "competitors": {
          "Insightspark": true
        },
        "status": "GAP"
      },
      {
        "topic": "how to build nps tracking",
        "target": false,
        "competitors": {
          "Insightspark": true
        },
        "status": "GAP"
      },
      {
        "topic": "what is self-serve analytics",
        "target": false,
        "competitors": {
          "Insightspark": true
        },
        "status": "GAP"
      },
      {
        "topic": "voice of customer framework",
        "target": false,
        "competitors": {
          "Insightspark": true
        },
        "status": "GAP"
      },
      {
        "topic": "customer health scoring",
        "target": false,
        "competitors": {
          "Insightspark": true
        },
        "status": "GAP"
      },
      {
        "topic": "gdpr-compliant analytics",
        "target": false,
        "competitors": {
          "Insightspark": true
        },
        "status": "GAP"
      },
      {
        "topic": "free-to-paid conversion tracking",
        "target": false,
        "competitors": {
          "Insightspark": true
        },
        "status": "GAP"
      },
      {
        "topic": "conversion rate benchmarks",
        "target": false,
        "competitors": {
          "Insightspark": true
        },
        "status": "GAP"
      },
      {
        "topic": "best session replay tools",
        "target": false,
        "competitors": {
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "best heatmap tools",
        "target": false,
        "competitors": {
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "best mobile analytics tools",
        "target": false,
        "competitors": {
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "heatmap analytics",
        "target": false,
        "competitors": {
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "multi-touch attribution modeling",
        "target": false,
        "competitors": {
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "reverse etl",
        "target": false,
        "competitors": {
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "onboarding funnel optimization",
        "target": false,
        "competitors": {
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "funnel drop-off analysis",
        "target": false,
        "competitors": {
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "product-led seo strategy",
        "target": false,
        "competitors": {
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "push notification strategy",
        "target": false,
        "competitors": {
          "Pulsegrid": true
        },
        "status": "GAP"
      },
      {
        "topic": "email engagement tracking setup",
        "target": false,
        "competitors": {
          "Pulsegrid": true
        },
        "status": "GAP"
      }
    ]
  }
};

const SEVERITY_COLOR = { critical: "#ef4444", high: "#eab308", moderate: "#22c55e" };
const PRIORITY_COLOR = { P1: "bg-red-500/15 text-red-400 border-red-500/30",
                          P2: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
                          P3: "bg-blue-500/15 text-blue-400 border-blue-500/30" };
const INTENT_COLOR = { comparison: "#a78bfa", howto: "#60a5fa", definition: "#34d399",
                        framework: "#fb923c", examples: "#facc15", metrics: "#22d3ee",
                        checklist: "#c4b5fd", guide: "#818cf8" };
const HEALTH_COLOR = { green: "#22c55e", yellow: "#eab308", red: "#ef4444", unknown: "#9ca3af" };

function Sparkline({ values }) {
  if (!values || values.length < 2) return null;
  const w = 120, h = 28;
  const min = Math.min(...values), max = Math.max(...values);
  const rng = Math.max(max - min, 1);
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (w - 4) + 2;
    const y = h - 2 - ((v - min) / rng) * (h - 4);
    return [x, y];
  });
  const polyPts = pts.map(([x, y]) => x.toFixed(1) + "," + y.toFixed(1)).join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg width={w} height={h} viewBox={"0 0 " + w + " " + h}>
      <polyline fill="none" stroke="#818cf8" strokeWidth="2" points={polyPts} />
      <circle cx={last[0]} cy={last[1]} r="2.5" fill="#818cf8" />
    </svg>
  );
}

function Delta({ value }) {
  if (value == null) return null;
  if (value === 0) return <span className="text-gray-500 text-xs">— no change</span>;
  const up = value > 0;
  const cls = up ? "text-green-400" : "text-red-400";
  const arrow = up ? "▲" : "▼";
  return <span className={cls + " text-xs font-semibold"}>{arrow} {Math.abs(value)} vs last run</span>;
}

function HealthHero({ health }) {
  if (!health || health.composite == null) {
    return (
      <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-12 text-center text-gray-400">
        <div className="text-3xl mb-2 opacity-40">∅</div>
        <div className="text-gray-200 mb-1">Site health not computed</div>
        <div className="text-xs">Run the pipeline to populate this view.</div>
      </div>
    );
  }
  const lbl = health.composite_label || "unknown";
  const color = HEALTH_COLOR[lbl] || HEALTH_COLOR.unknown;
  const subs = health.subscores || {};
  const deltas = health.deltas || {};
  const subLabels = {
    coverage: "Topic Coverage",
    cannibalization: "Cannibalization",
    freshness: "Freshness",
    brand: "Brand Voice",
    competitive: "Competitive",
  };
  return (
    <div className="rounded-xl border border-gray-700 bg-gradient-to-br from-gray-800 to-gray-900 p-6 mb-5">
      <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] gap-6 items-center">
        <div className="text-center">
          <div className="text-7xl font-extrabold leading-none" style={{ color }}>{health.composite}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-widest mt-1 font-semibold">Site Health / 100</div>
          <div className="mt-2"><Delta value={deltas.composite} /></div>
          {health.sparkline && health.sparkline.length > 1 && (
            <div className="flex items-center gap-2 justify-center mt-2">
              <Sparkline values={health.sparkline} />
              <span className="text-[10px] text-gray-500">last {health.sparkline.length} runs</span>
            </div>
          )}
        </div>
        <div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold mb-3">Subscores · weighted composite</div>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {Object.entries(subLabels).map(([key, label]) => {
              const s = subs[key];
              if (!s) return null;
              const c = HEALTH_COLOR[s.label] || HEALTH_COLOR.unknown;
              const d = deltas[key];
              return (
                <div key={key} className="rounded-lg border border-gray-700 bg-gray-900/60 p-3">
                  <div className="text-[10px] text-gray-400 uppercase tracking-wide font-semibold">{label}</div>
                  <div className="flex justify-between items-baseline mt-1">
                    <div className="text-2xl font-bold" style={{ color: c }}>{s.score}</div>
                    {d != null && d !== 0 && (
                      <span className={d > 0 ? "text-green-400 text-xs font-semibold" : "text-red-400 text-xs font-semibold"}>
                        {d > 0 ? "▲" : "▼"} {Math.abs(d)}
                      </span>
                    )}
                  </div>
                  <div className="h-1 bg-gray-700 rounded mt-2 overflow-hidden">
                    <div className="h-full transition-all" style={{ width: s.score + "%", background: c }} />
                  </div>
                  <div className="text-[10.5px] text-gray-500 mt-1.5 leading-tight">{s.detail || ""}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCards({ stats }) {
  const cards = [
    { v: stats.urls, l: "URLs Analyzed", c: "text-indigo-400" },
    { v: stats.clusters, l: "Topic Clusters", c: "text-indigo-400" },
    { v: stats.cannib, l: "Cannibalization", c: "text-red-400" },
    { v: stats.ideas, l: "Content Briefs", c: "text-blue-400" },
    { v: stats.p1_ideas, l: "P1 Briefs", c: "text-yellow-400" },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-gray-700 rounded-lg overflow-hidden mb-5">
      {cards.map((c, i) => (
        <div key={i} className="bg-gray-800 p-4 text-center">
          <div className={"text-3xl font-bold " + c.c}>{c.v}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">{c.l}</div>
        </div>
      ))}
    </div>
  );
}

function Quadrant({ clusters, cannib }) {
  if (!clusters || !clusters.length) return null;
  const cannibMap = {};
  cannib.forEach((c) => { cannibMap[c.id] = c; });
  const points = clusters.map((c) => {
    const cm = cannibMap[c.id];
    return {
      name: c.name,
      x: c.urls,
      y: cm ? cm.count : 0,
      sev: cm ? cm.severity : "ok",
    };
  });
  const maxX = Math.max(...points.map((p) => p.x), 1);
  const maxY = Math.max(...points.map((p) => p.y), 1);
  const colorBy = (sev) => SEVERITY_COLOR[sev] || "#22c55e";
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 30 }}>
        <CartesianGrid stroke="#2a2d3a" strokeDasharray="3 3" />
        <XAxis type="number" dataKey="x" name="Pages" stroke="#9ca3af" tick={{ fontSize: 11 }}
               label={{ value: "Pages in cluster", position: "insideBottom", offset: -10, fill: "#9ca3af", fontSize: 11 }} />
        <YAxis type="number" dataKey="y" name="Cannibalized" stroke="#9ca3af" tick={{ fontSize: 11 }}
               label={{ value: "Cannibalized pages", angle: -90, position: "insideLeft", fill: "#9ca3af", fontSize: 11 }} />
        <ReferenceLine x={maxX / 2} stroke="#374151" strokeDasharray="3 3" />
        <ReferenceLine y={maxY / 2} stroke="#374151" strokeDasharray="3 3" />
        <Tooltip
          cursor={{ strokeDasharray: "3 3" }}
          contentStyle={{ background: "#1a1d27", border: "1px solid #374151", borderRadius: 6, fontSize: 12 }}
          formatter={(value, name) => [value, name === "x" ? "Pages" : "Cannibalized"]}
          labelFormatter={(_, payload) => payload && payload[0] ? payload[0].payload.name : ""}
        />
        <Scatter data={points}>
          {points.map((p, i) => <Cell key={i} fill={colorBy(p.sev)} />)}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

function CannibBar({ cannib }) {
  if (!cannib || !cannib.length) {
    return <div className="text-center text-gray-500 py-8 text-sm">No cannibalization detected.</div>;
  }
  const data = cannib.slice().reverse().map((c) => ({ name: c.name, count: c.count, severity: c.severity }));
  const colorOf = (sev) => SEVERITY_COLOR[sev] || "#22c55e";
  return (
    <ResponsiveContainer width="100%" height={Math.max(280, data.length * 30)}>
      <BarChart data={data} layout="vertical" margin={{ top: 10, right: 50, left: 150, bottom: 10 }}>
        <CartesianGrid stroke="#2a2d3a" strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" stroke="#9ca3af" tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" stroke="#e4e4e7" tick={{ fontSize: 11 }} width={140} />
        <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #374151", borderRadius: 6, fontSize: 12 }} />
        <Bar dataKey="count" radius={[0, 4, 4, 0]}>
          {data.map((d, i) => <Cell key={i} fill={colorOf(d.severity)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function CompetitorBar({ competitors }) {
  if (!competitors.rows || !competitors.rows.length) return null;
  const counts = { GAP: 0, SHARED: 0, ADVANTAGE: 0 };
  competitors.rows.forEach((r) => { counts[r.status] = (counts[r.status] || 0) + 1; });
  const data = [
    { name: "GAP", value: counts.GAP, fill: "#ef4444" },
    { name: "SHARED", value: counts.SHARED, fill: "#6366f1" },
    { name: "ADVANTAGE", value: counts.ADVANTAGE, fill: "#22c55e" },
  ];
  return (
    <ResponsiveContainer width="100%" height={130}>
      <BarChart data={data} layout="vertical" margin={{ top: 5, right: 40, left: 80, bottom: 10 }}>
        <CartesianGrid stroke="#2a2d3a" strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" stroke="#9ca3af" tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" stroke="#e4e4e7" tick={{ fontSize: 11 }} width={70} />
        <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #374151", borderRadius: 6, fontSize: 12 }} />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function Tab({ active, onClick, label, badge, badgeColor }) {
  return (
    <button
      onClick={onClick}
      className={"px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors border-b-2 " +
        (active ? "text-indigo-400 border-indigo-400" : "text-gray-500 border-transparent hover:text-gray-200")}
    >
      {label}
      {badge != null && (
        <span className={"ml-1.5 px-1.5 py-0.5 rounded text-[10px] " + (badgeColor || "bg-indigo-500/15 text-indigo-400")}>
          {badge}
        </span>
      )}
    </button>
  );
}

function SummaryTab({ data }) {
  const findings = [];
  if (data.stats.cannib) findings.push({ label: "Critical", color: "bg-red-500/15 text-red-400", text: data.stats.cannib + " clusters cannibalized" });
  if (data.stats.p1_ideas) findings.push({ label: "Opportunity", color: "bg-blue-500/15 text-blue-400", text: data.stats.p1_ideas + " P1 content briefs ready (validated by 2+ competitors)" });
  if (data.stats.clusters) findings.push({ label: "Strength", color: "bg-green-500/15 text-green-400", text: data.stats.clusters + " topic clusters identified" });
  return (
    <div>
      <HealthHero health={data.health} />
      <StatCards stats={data.stats} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-lg border border-gray-700 bg-gray-800 p-5">
          <div className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-3">Key Findings</div>
          <div className="space-y-2 text-sm">
            {findings.length ? findings.map((f, i) => (
              <div key={i}>
                <span className={"px-2 py-0.5 rounded text-[11px] font-semibold " + f.color}>{f.label}</span>
                <span className="ml-2 text-gray-200">{f.text}</span>
              </div>
            )) : <div className="text-gray-500 text-sm">No findings yet.</div>}
          </div>
        </div>
        <div className="rounded-lg border border-gray-700 bg-gray-800 p-5">
          <div className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-3">Topic Cluster Quadrant</div>
          <Quadrant clusters={data.clusters} cannib={data.cannib} />
          <div className="text-[10px] text-gray-500 mt-2 text-center">x: pages in cluster · y: cannibalized pages · top-right = consolidate first</div>
        </div>
      </div>
    </div>
  );
}

function ContentIdeasTab({ ideas }) {
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState({});
  if (!ideas || !ideas.length) {
    return (
      <div className="rounded-xl border-2 border-dashed border-gray-700 p-12 text-center text-gray-400">
        <div className="text-3xl mb-2 opacity-40">∅</div>
        <div className="text-gray-200 mb-1">No content briefs yet</div>
        <div className="text-xs">Re-run the pipeline with <code className="bg-gray-800 px-1.5 py-0.5 rounded text-[11px]">--competitor</code>.</div>
      </div>
    );
  }
  const fl = filter.toLowerCase();
  const rows = ideas.filter((i) =>
    !fl || i.title.toLowerCase().includes(fl) || i.topic.toLowerCase().includes(fl) || i.type.toLowerCase().includes(fl)
  );
  const counts = { P1: 0, P2: 0, P3: 0 };
  ideas.forEach((i) => { counts[i.priority] = (counts[i.priority] || 0) + 1; });
  return (
    <div>
      <div className="grid grid-cols-4 gap-px bg-gray-700 rounded-lg overflow-hidden mb-4">
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-indigo-400">{ideas.length}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">Total Briefs</div>
        </div>
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-red-400">{counts.P1}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">P1</div>
        </div>
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-yellow-400">{counts.P2}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">P2</div>
        </div>
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-blue-400">{counts.P3}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">P3</div>
        </div>
      </div>
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Search briefs by title, topic, or content type..."
        className="w-full px-4 py-2.5 rounded-lg bg-gray-800 border border-gray-700 text-gray-200 text-sm placeholder-gray-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none mb-3"
      />
      <div className="space-y-2.5">
        {rows.map((i, idx) => {
          const isOpen = !!expanded[idx];
          return (
            <div
              key={idx}
              onClick={() => setExpanded({ ...expanded, [idx]: !isOpen })}
              className="rounded-lg border border-gray-700 bg-gray-800 p-4 cursor-pointer hover:border-gray-600 transition-colors"
            >
              <div className="flex justify-between items-start gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <span className={"px-2 py-0.5 rounded text-[11px] font-semibold border " + PRIORITY_COLOR[i.priority]}>
                      {i.priority}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-semibold"
                          style={{ background: (INTENT_COLOR[i.intent] || "#6366f1") + "22", color: INTENT_COLOR[i.intent] || "#818cf8" }}>
                      {i.type}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] bg-gray-700 text-gray-400">{i.words}w</span>
                    <span className="text-[11px] text-gray-500">covered by: {i.covered_by}</span>
                  </div>
                  <div className="font-semibold text-gray-100 text-sm leading-snug">{i.title}</div>
                  <div className="text-[12px] text-gray-500 mt-1">
                    Gap topic: <em>{i.topic}</em> · Audience: {i.audience}
                  </div>
                </div>
                <span className={"text-gray-500 transition-transform " + (isOpen ? "rotate-90" : "")}>▶</span>
              </div>
              {isOpen && (
                <div className="mt-3 pt-3 border-t border-gray-700 grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">Target keywords</div>
                    <div className="flex flex-wrap gap-1.5">
                      {i.keywords.map((k, kIdx) => (
                        <span key={kIdx} className="px-2 py-0.5 rounded text-[11px] bg-blue-500/15 text-blue-400">{k}</span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">Key questions to answer</div>
                    <ul className="text-[12px] text-gray-300 space-y-1 list-disc pl-5">
                      {i.questions.map((q, qIdx) => <li key={qIdx}>{q}</li>)}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CannibTab({ cannib }) {
  const [expanded, setExpanded] = useState({});
  if (!cannib || !cannib.length) {
    return (
      <div className="rounded-xl border-2 border-dashed border-gray-700 p-12 text-center text-gray-400">
        <div className="text-3xl mb-2 opacity-40">∅</div>
        <div className="text-gray-200">No cannibalization detected — clean topical structure.</div>
      </div>
    );
  }
  return (
    <div>
      <div className="rounded-lg border border-gray-700 bg-gray-800 p-5 mb-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-3">Cannibalization by cluster</div>
        <div className="overflow-y-auto" style={{ maxHeight: 500 }}>
          <CannibBar cannib={cannib} />
        </div>
      </div>
      <div className="space-y-2.5">
        {cannib.map((c, idx) => {
          const isOpen = !!expanded[idx];
          const sevColor = SEVERITY_COLOR[c.severity];
          const sevBg = c.severity === "critical" ? "bg-red-500/15 text-red-400" :
                        c.severity === "high" ? "bg-yellow-500/15 text-yellow-400" : "bg-green-500/15 text-green-400";
          return (
            <div
              key={idx}
              onClick={() => setExpanded({ ...expanded, [idx]: !isOpen })}
              className="rounded-lg border border-gray-700 bg-gray-800 p-4 cursor-pointer hover:border-gray-600"
              style={{ borderLeftWidth: 3, borderLeftColor: sevColor }}
            >
              <div className="flex justify-between items-center">
                <strong className="text-gray-100 text-sm">{c.name}</strong>
                <div className="flex items-center gap-2">
                  <span className={"px-2 py-0.5 rounded text-[11px] font-semibold " + sevBg}>
                    {c.count} URLs · {c.severity}
                  </span>
                  <span className={"text-gray-500 transition-transform " + (isOpen ? "rotate-90" : "")}>▶</span>
                </div>
              </div>
              {isOpen && (
                <div className="mt-3 pt-3 border-t border-gray-700">
                  <div className="text-[11px] text-gray-500 mb-2">Sample of competing URLs:</div>
                  <ul className="text-[12px] text-blue-400 space-y-1">
                    {c.urls.map((u, uIdx) => <li key={uIdx}>{u}</li>)}
                    {c.more > 0 && <li className="text-gray-500">…and {c.more} more</li>}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CompetitorsTab({ competitors, siteName }) {
  const [filter, setFilter] = useState("");
  if (!competitors.rows || !competitors.rows.length) {
    return (
      <div className="rounded-xl border-2 border-dashed border-gray-700 p-12 text-center text-gray-400">
        <div className="text-3xl mb-2 opacity-40">∅</div>
        <div className="text-gray-200 mb-1">No competitor data</div>
        <div className="text-xs">Re-run with <code className="bg-gray-800 px-1.5 py-0.5 rounded text-[11px]">--competitor &lt;domain&gt;</code>.</div>
      </div>
    );
  }
  const counts = { GAP: 0, SHARED: 0, ADVANTAGE: 0 };
  competitors.rows.forEach((r) => { counts[r.status] = (counts[r.status] || 0) + 1; });
  const fl = filter.toLowerCase();
  const rows = competitors.rows.filter((r) => !fl || r.topic.toLowerCase().includes(fl));
  return (
    <div>
      <div className="grid grid-cols-3 gap-px bg-gray-700 rounded-lg overflow-hidden mb-4">
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-green-400">{counts.ADVANTAGE}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">{siteName} Advantages</div>
        </div>
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-blue-400">{counts.SHARED}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">Shared Topics</div>
        </div>
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-red-400">{counts.GAP}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">Content Gaps</div>
        </div>
      </div>
      <div className="rounded-lg border border-gray-700 bg-gray-800 p-4 mb-4">
        <CompetitorBar competitors={competitors} />
      </div>
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Search topics..."
        className="w-full px-4 py-2.5 rounded-lg bg-gray-800 border border-gray-700 text-gray-200 text-sm placeholder-gray-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none mb-3"
      />
      <div className="rounded-lg border border-gray-700 overflow-hidden">
        <div className="max-h-[500px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-900 sticky top-0">
              <tr>
                <th className="text-left px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">Topic</th>
                <th className="text-center px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">{siteName}</th>
                {competitors.names.map((n) => (
                  <th key={n} className="text-center px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">{n}</th>
                ))}
                <th className="text-left px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, idx) => {
                const statusCls = r.status === "GAP" ? "bg-red-500/15 text-red-400" :
                                  r.status === "ADVANTAGE" ? "bg-green-500/15 text-green-400" : "bg-blue-500/15 text-blue-400";
                return (
                  <tr key={idx} className="border-t border-gray-700 hover:bg-gray-700/30">
                    <td className="px-3 py-2 text-gray-200">{r.topic}</td>
                    <td className="px-3 py-2 text-center text-gray-400">{r.target ? "Y" : ""}</td>
                    {competitors.names.map((n) => (
                      <td key={n} className="px-3 py-2 text-center text-gray-400">{r.competitors && r.competitors[n] ? "Y" : ""}</td>
                    ))}
                    <td className="px-3 py-2"><span className={"px-2 py-0.5 rounded text-[11px] font-semibold " + statusCls}>{r.status}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ClustersTab({ clusters }) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState("urls");
  const [sortAsc, setSortAsc] = useState(false);
  if (!clusters || !clusters.length) {
    return <div className="text-gray-500 text-center py-12">No clusters.</div>;
  }
  const fl = filter.toLowerCase();
  const sortedRows = clusters
    .filter((c) => !fl || c.name.toLowerCase().includes(fl) || (c.keywords || "").toLowerCase().includes(fl))
    .slice()
    .sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (typeof av === "number") return sortAsc ? av - bv : bv - av;
      return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  const SortHead = ({ k, label, num }) => (
    <th
      onClick={() => { if (sortKey === k) setSortAsc(!sortAsc); else { setSortKey(k); setSortAsc(false); } }}
      className="text-left px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium cursor-pointer hover:text-gray-200"
    >
      {label} {sortKey === k ? (sortAsc ? "↑" : "↓") : ""}
    </th>
  );
  return (
    <div>
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Search clusters by name or keyword..."
        className="w-full px-4 py-2.5 rounded-lg bg-gray-800 border border-gray-700 text-gray-200 text-sm placeholder-gray-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none mb-3"
      />
      <div className="rounded-lg border border-gray-700 overflow-hidden">
        <div className="max-h-[600px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-900 sticky top-0">
              <tr>
                <SortHead k="id" label="ID" />
                <SortHead k="name" label="Cluster" />
                <SortHead k="urls" label="URLs" num />
                <th className="text-left px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">Keywords</th>
                <th className="text-left px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((c) => (
                <tr key={c.id} className="border-t border-gray-700 hover:bg-gray-700/30">
                  <td className="px-3 py-2 text-gray-400">{c.id}</td>
                  <td className="px-3 py-2 text-gray-100 font-medium">{c.name}</td>
                  <td className="px-3 py-2 text-gray-300">{c.urls}</td>
                  <td className="px-3 py-2 text-gray-500 text-[12px] max-w-[280px] truncate" title={c.keywords}>{c.keywords}</td>
                  <td className="px-3 py-2">
                    {c.cannibalized
                      ? <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-red-500/15 text-red-400">Cannibalized</span>
                      : <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-green-500/15 text-green-400">OK</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function TopicalAuthorityDashboard() {
  const [tab, setTab] = useState("summary");
  const TABS = [
    { id: "summary", label: "Summary" },
    { id: "ideas", label: "Content Ideas", badge: DATA.stats.ideas, color: "bg-indigo-500/15 text-indigo-400" },
    { id: "cannib", label: "Cannibalization", badge: DATA.stats.cannib, color: "bg-red-500/15 text-red-400" },
    { id: "competitors", label: "Competitors" },
    { id: "clusters", label: "Topic Clusters", badge: DATA.stats.clusters, color: "bg-indigo-500/15 text-indigo-400" },
  ];
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100" style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>
      <div className="bg-gray-900 border-b border-gray-700 px-6 py-4 flex justify-between items-center">
        <div>
          <h1 className="text-lg font-bold">Topical Authority Audit</h1>
          <div className="text-xs text-gray-400">{DATA.site.domain}</div>
        </div>
        <div className="text-xs text-gray-400 text-right">
          {DATA.site.name}{DATA.site.industry ? " · " + DATA.site.industry : ""}<br />
          {DATA.stats.urls} pages analyzed
        </div>
      </div>
      <div className="bg-gray-900 border-b border-gray-700 flex overflow-x-auto px-4 sticky top-0 z-10">
        {TABS.map((t) => (
          <Tab key={t.id} active={tab === t.id} onClick={() => setTab(t.id)} label={t.label} badge={t.badge} badgeColor={t.color} />
        ))}
      </div>
      <div className="p-6">
        {tab === "summary" && <SummaryTab data={DATA} />}
        {tab === "ideas" && <ContentIdeasTab ideas={DATA.ideas} />}
        {tab === "cannib" && <CannibTab cannib={DATA.cannib} />}
        {tab === "competitors" && <CompetitorsTab competitors={DATA.competitors} siteName={DATA.site.name} />}
        {tab === "clusters" && <ClustersTab clusters={DATA.clusters} />}
      </div>
      <div className="border-t border-gray-700 px-6 py-3 text-center text-[11px] text-gray-500">
        Topical Authority Mapper · {DATA.site.name}
      </div>
    </div>
  );
}
