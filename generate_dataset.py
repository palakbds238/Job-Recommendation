"""
generate_dataset.py
-------------------
Generates a realistic CSV dataset of 120 job postings for the ML model.
Run this once before training the model.
"""

import pandas as pd
import random

random.seed(42)

# ── Job templates by category ──────────────────────────────────────────────────
job_data = [

    # SOFTWARE ENGINEERING
    ("Software Engineer", "TCS", "Python, Java, SQL, Git, REST APIs", "Software Engineering",
     "Develop and maintain scalable backend services. Collaborate with cross-functional teams.", "Bangalore"),
    ("Backend Developer", "Infosys", "Node.js, Express, MongoDB, Docker, REST APIs", "Software Engineering",
     "Build robust APIs and microservices. Optimize database queries.", "Hyderabad"),
    ("Full Stack Developer", "Wipro", "React, Node.js, PostgreSQL, AWS, Docker", "Software Engineering",
     "Design and implement end-to-end web applications using modern tech stack.", "Pune"),
    ("Java Developer", "HCL Technologies", "Java, Spring Boot, Hibernate, MySQL, Maven", "Software Engineering",
     "Develop enterprise Java applications. Write clean, testable code.", "Chennai"),
    ("Python Developer", "Capgemini", "Python, Django, Flask, PostgreSQL, Redis", "Software Engineering",
     "Build Python-based web applications and automation scripts.", "Mumbai"),
    ("Software Developer", "Tech Mahindra", "C++, Java, Linux, Git, Agile", "Software Engineering",
     "Develop software components for enterprise products.", "Noida"),
    ("Backend Engineer", "Freshworks", "Golang, Kubernetes, gRPC, PostgreSQL", "Software Engineering",
     "Build high-performance backend systems serving millions of users.", "Chennai"),
    ("API Developer", "Mphasis", "REST APIs, Python, Flask, OAuth, Swagger", "Software Engineering",
     "Design and implement RESTful APIs for client-facing products.", "Bangalore"),
    ("Software Engineer II", "Zoho", "Java, Spring, MySQL, Redis, Kafka", "Software Engineering",
     "Build scalable SaaS products used by global customers.", "Chennai"),
    ("Systems Engineer", "L&T Technology", "C, Linux, Embedded Systems, RTOS", "Software Engineering",
     "Develop embedded software for industrial automation solutions.", "Mysore"),
    ("Applications Developer", "Oracle", "PL/SQL, Java, Oracle DB, REST", "Software Engineering",
     "Develop Oracle cloud applications and integrations.", "Hyderabad"),
    ("Software Developer", "Mindtree", "Python, Angular, MongoDB, Azure", "Software Engineering",
     "Implement features for cloud-native enterprise applications.", "Bangalore"),

    # DATA SCIENCE / AI / ML
    ("Data Scientist", "Flipkart", "Python, Machine Learning, TensorFlow, SQL, Statistics", "Data Science",
     "Build ML models to optimize pricing and recommendations for e-commerce.", "Bangalore"),
    ("Machine Learning Engineer", "Ola", "Python, Scikit-learn, Deep Learning, Spark", "Data Science",
     "Develop ML pipelines for ride demand forecasting and route optimization.", "Bangalore"),
    ("AI Engineer", "Razorpay", "Python, NLP, PyTorch, Transformers, FastAPI", "Data Science",
     "Build AI-powered fraud detection and financial intelligence models.", "Bangalore"),
    ("Data Analyst", "Swiggy", "Python, SQL, Tableau, Excel, Statistics", "Data Science",
     "Analyze delivery operations data and build actionable dashboards.", "Bangalore"),
    ("ML Researcher", "Samsung R&D", "Python, Deep Learning, Computer Vision, OpenCV", "Data Science",
     "Research and implement state-of-the-art AI algorithms for mobile devices.", "Noida"),
    ("NLP Engineer", "Niki.ai", "Python, NLP, BERT, spaCy, Rasa", "Data Science",
     "Build conversational AI systems and intent classification models.", "Bangalore"),
    ("Business Intelligence Analyst", "Myntra", "SQL, Power BI, Python, Excel, Tableau", "Data Science",
     "Create reports and dashboards to support business decisions.", "Bangalore"),
    ("Data Engineer", "Paytm", "Spark, Kafka, Python, Hadoop, AWS", "Data Science",
     "Build data pipelines and ETL processes for financial data.", "Noida"),
    ("Computer Vision Engineer", "Niramai", "Python, OpenCV, TensorFlow, PyTorch, CNN", "Data Science",
     "Develop medical image analysis algorithms for cancer screening.", "Bangalore"),
    ("Data Scientist", "Meesho", "Python, A/B Testing, SQL, ML, Statistics", "Data Science",
     "Run experiments and build models to grow social commerce platform.", "Bangalore"),
    ("Analytics Engineer", "CRED", "dbt, SQL, Airflow, Python, BigQuery", "Data Science",
     "Build and maintain analytical models for fintech product analytics.", "Bangalore"),
    ("AI/ML Engineer", "Haptik", "Python, NLP, BERT, Transformers, FastAPI", "Data Science",
     "Develop conversational AI products for enterprise clients.", "Mumbai"),

    # WEB DEVELOPMENT
    ("Frontend Developer", "Zomato", "React, JavaScript, CSS, HTML, TypeScript", "Web Development",
     "Build beautiful and responsive UI for food delivery platform.", "Gurgaon"),
    ("React Developer", "Naukri.com", "React, Redux, JavaScript, REST APIs, Jest", "Web Development",
     "Develop modern job portal interfaces using React ecosystem.", "Noida"),
    ("Angular Developer", "Persistent Systems", "Angular, TypeScript, RxJS, HTML, CSS", "Web Development",
     "Build enterprise web applications using Angular framework.", "Pune"),
    ("Vue.js Developer", "Druva", "Vue.js, JavaScript, CSS3, REST APIs, Git", "Web Development",
     "Develop cloud backup management interfaces with Vue.js.", "Pune"),
    ("UI Developer", "InMobi", "HTML, CSS, JavaScript, React, Webpack", "Web Development",
     "Create pixel-perfect ad tech UI components and dashboards.", "Bangalore"),
    ("WordPress Developer", "WPWeb Infotech", "WordPress, PHP, CSS, JavaScript, MySQL", "Web Development",
     "Develop custom WordPress themes and plugins for clients.", "Ahmedabad"),
    ("Web Designer", "Fractal Analytics", "Figma, HTML, CSS, JavaScript, UX Design", "Web Development",
     "Design and prototype web interfaces for analytics products.", "Mumbai"),
    ("MERN Stack Developer", "BrowserStack", "MongoDB, Express, React, Node.js, REST", "Web Development",
     "Build full-stack JavaScript applications for developer tools.", "Mumbai"),
    ("Shopify Developer", "Headstart", "Shopify, Liquid, JavaScript, CSS, APIs", "Web Development",
     "Customize Shopify stores and develop apps for e-commerce clients.", "Remote"),
    ("PHP Developer", "Nagarro", "PHP, Laravel, MySQL, REST APIs, Git", "Web Development",
     "Build web applications and APIs using PHP/Laravel stack.", "Gurgaon"),

    # MOBILE DEVELOPMENT
    ("Android Developer", "BYJU'S", "Kotlin, Java, Android SDK, REST APIs, SQLite", "Mobile Development",
     "Build educational Android apps used by 10 million students.", "Bangalore"),
    ("iOS Developer", "Cleartrip", "Swift, SwiftUI, Xcode, REST APIs, Core Data", "Mobile Development",
     "Develop travel booking iOS applications with great UX.", "Mumbai"),
    ("Flutter Developer", "PhonePe", "Flutter, Dart, Firebase, REST APIs, BLoC", "Mobile Development",
     "Build cross-platform mobile features for UPI payment app.", "Bangalore"),
    ("React Native Developer", "Unacademy", "React Native, JavaScript, Redux, Firebase", "Mobile Development",
     "Build cross-platform learning apps for education platform.", "Bangalore"),
    ("Mobile Engineer", "Dream11", "Kotlin, Swift, REST APIs, Firebase, WebSocket", "Mobile Development",
     "Develop high-performance fantasy sports mobile applications.", "Mumbai"),

    # CLOUD / DEVOPS
    ("DevOps Engineer", "Nutanix", "AWS, Docker, Kubernetes, CI/CD, Terraform", "Cloud & DevOps",
     "Build and maintain cloud infrastructure and deployment pipelines.", "Bangalore"),
    ("Cloud Engineer", "Rackspace", "AWS, Azure, GCP, Terraform, Linux", "Cloud & DevOps",
     "Design and implement cloud architectures for enterprise clients.", "Mumbai"),
    ("SRE Engineer", "Atlassian", "Linux, Python, Kubernetes, Prometheus, Go", "Cloud & DevOps",
     "Ensure reliability and scalability of distributed systems.", "Bangalore"),
    ("AWS Solutions Architect", "Accenture", "AWS, Cloud Architecture, Security, Networking", "Cloud & DevOps",
     "Design AWS cloud solutions for large enterprise migrations.", "Hyderabad"),
    ("Kubernetes Engineer", "Palo Alto Networks", "Kubernetes, Docker, Helm, Istio, Go", "Cloud & DevOps",
     "Manage large-scale Kubernetes clusters for security products.", "Bangalore"),
    ("CI/CD Engineer", "GlobalLogic", "Jenkins, GitHub Actions, Docker, Ansible, Linux", "Cloud & DevOps",
     "Build automation pipelines and streamline software delivery.", "Noida"),

    # CYBERSECURITY
    ("Cybersecurity Analyst", "Deloitte", "Network Security, SIEM, Python, Threat Analysis", "Cybersecurity",
     "Monitor security events and respond to threats for enterprise clients.", "Mumbai"),
    ("Penetration Tester", "KPMG", "Kali Linux, Metasploit, Python, Network Security", "Cybersecurity",
     "Conduct ethical hacking assessments for financial institutions.", "Gurgaon"),
    ("SOC Analyst", "IBM Security", "SIEM, Splunk, Incident Response, Network Security", "Cybersecurity",
     "Monitor and respond to security incidents in 24x7 SOC environment.", "Pune"),
    ("Application Security Engineer", "PayU", "OWASP, Python, Burp Suite, Code Review", "Cybersecurity",
     "Embed security practices in development and conduct appsec reviews.", "Gurgaon"),

    # DATABASE / DATA ENGINEERING
    ("Database Administrator", "Yatra", "MySQL, Oracle, Backup, Performance Tuning, Linux", "Database",
     "Manage and optimize relational databases for travel portal.", "Gurgaon"),
    ("MongoDB Developer", "MakeMyTrip", "MongoDB, Python, Node.js, Redis, Aggregation", "Database",
     "Design MongoDB schemas and optimize queries for travel data.", "Gurgaon"),
    ("SQL Developer", "Muthoot Finance", "SQL Server, T-SQL, SSRS, ETL, Performance Tuning", "Database",
     "Develop SQL queries and reports for financial data warehouse.", "Kochi"),
    ("Data Warehouse Engineer", "EY", "Redshift, SQL, Python, ETL, BI Tools", "Database",
     "Build and maintain cloud data warehouses for analytics.", "Bangalore"),

    # PRODUCT MANAGEMENT
    ("Product Manager", "Urban Company", "Product Strategy, Agile, Data Analysis, SQL", "Product Management",
     "Define product roadmap for home services marketplace.", "Gurgaon"),
    ("Associate Product Manager", "Dunzo", "User Research, Figma, SQL, Agile, Analytics", "Product Management",
     "Work on hyperlocal delivery product with strong data focus.", "Bangalore"),
    ("Technical Product Manager", "Hasura", "APIs, GraphQL, SQL, Product Strategy, Agile", "Product Management",
     "Manage developer-focused open-source database product.", "Bangalore"),
    ("Product Analyst", "Lenskart", "SQL, Python, A/B Testing, Product Analytics", "Product Management",
     "Analyze customer journeys and improve eyewear shopping product.", "Gurgaon"),

    # DESIGN / UX
    ("UX Designer", "Razorpay", "Figma, User Research, Prototyping, Design Systems", "Design",
     "Design intuitive payment experiences for millions of users.", "Bangalore"),
    ("UI/UX Designer", "ShareChat", "Figma, Adobe XD, User Research, HTML, CSS", "Design",
     "Create social media features for India's largest vernacular platform.", "Bangalore"),
    ("Product Designer", "Leadsquared", "Figma, Interaction Design, Usability Testing", "Design",
     "Design CRM product used by sales teams across industries.", "Bangalore"),
    ("Graphic Designer", "Wavemaker", "Illustrator, Photoshop, Figma, Branding", "Design",
     "Create visual assets for digital marketing campaigns.", "Mumbai"),
    ("Motion Designer", "Pocket FM", "After Effects, Figma, Animation, Premier Pro", "Design",
     "Create animations and motion graphics for audio platform.", "Bangalore"),

    # FINANCE / FINTECH
    ("Financial Analyst", "Groww", "Excel, Python, Financial Modeling, SQL, Tableau", "Finance",
     "Analyze investment products and build financial dashboards.", "Bangalore"),
    ("Quantitative Analyst", "Zerodha", "Python, Statistics, Algorithmic Trading, SQL", "Finance",
     "Build quantitative models for stock market analysis.", "Bangalore"),
    ("Risk Analyst", "ICICI Bank", "Excel, SQL, SAS, Risk Modeling, Statistics", "Finance",
     "Assess credit risk and build risk scorecards for lending.", "Mumbai"),
    ("Fintech Developer", "Slice", "Python, Blockchain, APIs, Security, SQL", "Finance",
     "Build fintech payment products for millennial users.", "Bangalore"),
    ("Chartered Accountant", "PwC", "Taxation, Accounting, Tally, Excel, Compliance", "Finance",
     "Provide audit and tax advisory services to corporate clients.", "Delhi"),

    # MARKETING / DIGITAL
    ("Digital Marketing Manager", "Nykaa", "SEO, SEM, Google Ads, Social Media, Analytics", "Marketing",
     "Drive digital customer acquisition for beauty e-commerce platform.", "Mumbai"),
    ("SEO Specialist", "Healthkart", "SEO, Google Analytics, Content, Python, Ahrefs", "Marketing",
     "Improve organic search rankings for health supplement platform.", "Gurgaon"),
    ("Growth Hacker", "Doubtnut", "Python, Analytics, A/B Testing, SQL, Marketing", "Marketing",
     "Drive user growth for EdTech platform through data-driven experiments.", "Noida"),
    ("Content Strategist", "Razorpay", "Content Writing, SEO, Analytics, Marketing Strategy", "Marketing",
     "Create content that educates fintech audience and drives conversions.", "Bangalore"),
    ("Performance Marketing", "MPL", "Facebook Ads, Google Ads, Analytics, SQL", "Marketing",
     "Manage paid campaigns for mobile gaming platform.", "Bangalore"),

    # HR / OPERATIONS
    ("HR Business Partner", "Infosys BPM", "HR Policies, Talent Acquisition, Excel, HRMS", "Human Resources",
     "Partner with business units to drive people strategy.", "Mysore"),
    ("Technical Recruiter", "Naukri", "Sourcing, LinkedIn, Excel, Communication, ATS", "Human Resources",
     "Hire top engineering talent for technology companies.", "Noida"),
    ("Operations Manager", "Delhivery", "Supply Chain, Excel, SQL, Operations, Analytics", "Operations",
     "Manage logistics operations across multiple fulfillment centers.", "Gurgaon"),
    ("Business Analyst", "Gartner", "Excel, SQL, Power BI, Business Analysis, Stakeholder Mgmt", "Business Analysis",
     "Analyze business requirements and recommend technology solutions.", "Gurgaon"),

    # FRESHER ROLES
    ("Junior Software Developer", "Cognizant", "Python, Java, SQL, Git, OOP", "Software Engineering",
     "Entry-level software development role with training and mentorship.", "Multiple Locations"),
    ("Trainee Data Analyst", "WNS Analytics", "Excel, SQL, Basic Python, Statistics", "Data Science",
     "Learn analytics tools and support senior analysts on client projects.", "Mumbai"),
    ("Graduate Engineer Trainee", "Bosch", "C, Embedded C, Electronics, MATLAB", "Software Engineering",
     "Rotational program across engineering teams with structured learning.", "Bangalore"),
    ("Junior Frontend Developer", "Razorpay", "HTML, CSS, JavaScript, React Basics, Git", "Web Development",
     "Build UI components under guidance of senior frontend engineers.", "Bangalore"),
    ("ML Intern", "Samsung PRISM", "Python, Scikit-learn, Jupyter, Statistics", "Data Science",
     "Contribute to ML research projects as part of university program.", "Noida"),
    ("Data Science Intern", "Tiger Analytics", "Python, SQL, Machine Learning, Statistics", "Data Science",
     "Work on real-world analytics projects with Fortune 500 clients.", "Chennai"),
    ("Software Testing Intern", "Qspiders", "Manual Testing, Selenium, Java, SQL, JIRA", "Software Testing",
     "Learn software testing methodologies and automation tools.", "Bangalore"),
    ("Android Intern", "ShareChat", "Kotlin, Android, REST APIs, Git", "Mobile Development",
     "Build features for India's largest social media platform.", "Bangalore"),

    # TESTING / QA
    ("QA Engineer", "Adobe", "Selenium, Java, TestNG, API Testing, SQL", "Software Testing",
     "Automate testing for creative cloud products.", "Noida"),
    ("SDET", "Microsoft", "Python, Selenium, REST APIs, CI/CD, Azure", "Software Testing",
     "Build test automation frameworks for Microsoft products.", "Hyderabad"),
    ("Manual Tester", "Nagarro", "Test Cases, Jira, Agile, Regression, SQL", "Software Testing",
     "Perform functional and regression testing for enterprise apps.", "Gurgaon"),

    # EMBEDDED / IoT
    ("Embedded Engineer", "Bosch", "C, RTOS, CAN, Linux, Embedded Linux", "Embedded Systems",
     "Develop embedded software for automotive control units.", "Coimbatore"),
    ("IoT Developer", "Siemens", "Python, MQTT, AWS IoT, C++, Linux", "Embedded Systems",
     "Build IoT solutions for industrial automation.", "Pune"),
    ("Firmware Engineer", "Honeywell", "C, Assembly, RTOS, Hardware Interfaces, Git", "Embedded Systems",
     "Develop firmware for HVAC and building automation devices.", "Hyderabad"),

    # BLOCKCHAIN
    ("Blockchain Developer", "Polygon", "Solidity, Ethereum, Web3.js, Python, Smart Contracts", "Blockchain",
     "Build decentralized applications on Polygon blockchain.", "Remote"),
    ("Smart Contract Engineer", "CoinDCX", "Solidity, Truffle, Hardhat, JavaScript, DeFi", "Blockchain",
     "Develop and audit smart contracts for crypto exchange.", "Mumbai"),

    # EXTRA DIVERSITY
    ("Technical Writer", "Postman", "Technical Writing, Markdown, API Docs, Python", "Technical Writing",
     "Create developer documentation for API platform used globally.", "Bangalore"),
    ("Scrum Master", "Thoughtworks", "Agile, Scrum, JIRA, Facilitation, Stakeholder Mgmt", "Project Management",
     "Facilitate agile ceremonies and remove impediments for dev teams.", "Bangalore"),
    ("Solutions Architect", "AWS India", "AWS, Cloud, Architecture, Python, Networking", "Cloud & DevOps",
     "Help enterprise customers design scalable cloud architectures.", "Gurgaon"),
    ("Research Scientist", "Microsoft Research", "Python, Deep Learning, Research, Statistics, PyTorch", "Data Science",
     "Conduct AI/ML research with global impact at world-class lab.", "Bangalore"),
    ("Platform Engineer", "Razorpay", "Go, Kubernetes, PostgreSQL, gRPC, Distributed Systems", "Software Engineering",
     "Build core infrastructure powering India's leading fintech platform.", "Bangalore"),
    ("Security Researcher", "Bug Crowd", "Python, Network Security, OSINT, Reverse Engineering", "Cybersecurity",
     "Find and report security vulnerabilities through bug bounty programs.", "Remote"),
    ("Data Governance Analyst", "Genpact", "SQL, Data Quality, Excel, Metadata, Policy", "Data Science",
     "Manage data governance frameworks for enterprise data assets.", "Noida"),
    ("Robotics Engineer", "Systemantics", "Python, ROS, C++, Computer Vision, Motion Planning", "Embedded Systems",
     "Develop robotics software for industrial automation arms.", "Bangalore"),
    ("Game Developer", "Nazara Technologies", "Unity, C#, Game Design, 3D Modeling, JavaScript", "Software Engineering",
     "Build mobile games played by millions across India.", "Mumbai"),
]

# ── Experience levels & salaries ──────────────────────────────────────────────
exp_options = ["0-1 years", "1-3 years", "3-5 years", "5-8 years", "8+ years"]
salary_map = {
    "0-1 years": ("3-5 LPA", 3, 5),
    "1-3 years": ("5-10 LPA", 5, 10),
    "3-5 years": ("10-18 LPA", 10, 18),
    "5-8 years": ("18-30 LPA", 18, 30),
    "8+ years": ("30-60 LPA", 30, 60),
}

education_map = {
    "Software Engineering": ["B.Tech", "B.Tech", "M.Tech", "BCA"],
    "Data Science": ["B.Tech", "M.Tech", "M.Sc.", "B.Tech", "PhD"],
    "Web Development": ["B.Tech", "BCA", "B.Sc.", "Self-taught"],
    "Mobile Development": ["B.Tech", "BCA", "MCA"],
    "Cloud & DevOps": ["B.Tech", "M.Tech", "B.Sc."],
    "Cybersecurity": ["B.Tech", "M.Tech", "B.Sc.", "Certified"],
    "Database": ["B.Tech", "BCA", "MCA", "B.Sc."],
    "Product Management": ["B.Tech", "MBA", "M.Tech"],
    "Design": ["B.Des", "B.Tech", "B.A.", "Self-taught"],
    "Finance": ["B.Com", "MBA", "CA", "M.Sc."],
    "Marketing": ["MBA", "B.A.", "B.Tech", "BBA"],
    "Human Resources": ["MBA", "BBA", "B.A.", "M.A."],
    "Operations": ["MBA", "B.Tech", "B.A."],
    "Business Analysis": ["MBA", "B.Tech", "M.Tech"],
    "Software Testing": ["B.Tech", "BCA", "B.Sc."],
    "Embedded Systems": ["B.Tech", "M.Tech", "Diploma"],
    "Blockchain": ["B.Tech", "M.Tech", "Self-taught"],
    "Technical Writing": ["B.Tech", "B.A.", "M.A."],
    "Project Management": ["B.Tech", "MBA", "PMP"],
}

rows = []
for i, (title, company, skills, category, desc, loc) in enumerate(job_data):
    # Assign experience level based on common sense
    if "Intern" in title or "Trainee" in title or "Junior" in title or "Graduate" in title:
        exp = "0-1 years"
    elif "Senior" in title or "Lead" in title or "Manager" in title or "Architect" in title or "Principal" in title:
        exp = random.choice(["5-8 years", "8+ years"])
    elif "Associate" in title or "II" in title or "Analyst" in title:
        exp = random.choice(["1-3 years", "3-5 years"])
    else:
        exp = random.choice(["1-3 years", "3-5 years", "3-5 years"])

    sal_range, sal_min, sal_max = salary_map[exp]
    sal_value = round(random.uniform(sal_min, sal_max), 1)

    edu_list = education_map.get(category, ["B.Tech"])
    edu = random.choice(edu_list)

    job_type = random.choice(["Full-time", "Full-time", "Full-time", "Hybrid", "Remote"])

    rows.append({
        "job_id": i + 1,
        "title": title,
        "company": company,
        "skills_required": skills,
        "category": category,
        "description": desc,
        "location": loc,
        "experience_required": exp,
        "education_required": edu,
        "salary_range": sal_range,
        "salary_lpa": sal_value,
        "job_type": job_type,
        "openings": random.randint(1, 10),
        "posted_days_ago": random.randint(0, 30),
    })

df = pd.DataFrame(rows)
df.to_csv("/home/claude/job_recommender/data/jobs.csv", index=False)
print(f"✅ Dataset generated: {len(df)} jobs across {df['category'].nunique()} categories")
print(df['category'].value_counts())
