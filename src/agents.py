"""10 AI Agents."""

from crewai import Agent


def create_agents():
    return {
        "data_analytics": Agent(
            role="Data Analytics Specialist",
            goal="Ingest and pipeline data",
            backstory="Expert in ETL and data quality.",
            verbose=True,
        ),
        "profit_architect": Agent(
            role="Profit Architect",
            goal="Compute financial KPIs and ROI",
            backstory="Expert in e-commerce finance.",
            verbose=True,
        ),
        "supply_chain": Agent(
            role="Supply Chain Lead",
            goal="Monitor inventory",
            backstory="Supply chain optimization expert.",
            verbose=True,
        ),
        "trend_forecaster": Agent(
            role="Trend Forecaster",
            goal="Identify viral product opportunities",
            backstory="Data scientist specializing in behavioral signals.",
            verbose=True,
        ),
        "product_sourcing": Agent(
            role="Product Sourcing Scout",
            goal="Map trends to vendor SKUs",
            backstory="Procurement specialist.",
            verbose=True,
        ),
        "ad_specialist": Agent(
            role="TikTok Ad Specialist",
            goal="Generate high-retention ad scripts",
            backstory="Creative strategist with virality expertise.",
            verbose=True,
        ),
        "creative_prompt": Agent(
            role="Creative Prompt Engineer",
            goal="Convert scripts to visual prompts",
            backstory="AI prompt optimization specialist.",
            verbose=True,
        ),
        "lifecycle_marketer": Agent(
            role="Lifecycle Marketer",
            goal="Design email retention journeys",
            backstory="Email marketing strategist.",
            verbose=True,
        ),
        "meta_retargeting": Agent(
            role="Meta Retargeting Engine",
            goal="Build lookalike audiences",
            backstory="Meta advertising expert.",
            verbose=True,
        ),
        "customer_experience": Agent(
            role="Customer Experience Specialist",
            goal="Triage tickets and flag compliance issues",
            backstory="Customer operations expert.",
            verbose=True,
        ),
    }