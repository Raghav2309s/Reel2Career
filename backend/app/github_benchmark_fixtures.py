from backend.app.resource_verifier import GitHubRepositoryCandidate


def candidate(
    owner,
    repository,
    description="",
    topics=(),
    archived=False,
):
    return GitHubRepositoryCandidate(
        owner=owner,
        repository=repository,
        url=f"https://github.com/{owner}/{repository}",
        description=description,
        topics=topics,
        archived=archived,
    )


FIXTURES = {
    37: [
        candidate("faiza788", "idempotent-payment-gateway"),
        candidate("manasvi0209", "idempotent-payment-gateway"),
        candidate("Omenn6", "idempotent-payment-gateway"),
        candidate("rahulbitsgoa", "idempotent-payment-gateway"),
        candidate("Xprofess0r", "Idempotent-Payment-Gateway"),
        candidate("zgabrieloliveira", "idempotent-payment-gateway"),
        candidate(
            "kavyagupta03july-svg",
            "idempotent-payment-gateway-main",
        ),
        candidate(
            "Glyneria",
            "Idempotent-Payment-Gateway-Wrapper",
        ),
        candidate(
            "ishitaR919",
            "SecurePay-IdempotentPaymentGateway",
        ),
        candidate(
            "MjavadBakhshi",
            "laravel-payment-gateway-idempotent",
        ),
    ],
    40: [
        candidate(
            "KeerthiKeswaran",
            "AI-Powered-Observability-and-Log-Analysis-System",
        ),
        candidate(
            "Gurita-Langit-Technologi",
            "AI-Powered-Observability-and-Log-Analysis-System",
        ),
        candidate(
            "architjain-05",
            "ai-incident-response-platform",
        ),
        candidate("nbkarthi", "log_monitor"),
        candidate(
            "irahgem",
            "agentic-rag-pipeline-intelligence",
        ),
        candidate(
            "iEric0228",
            "AI-SRE-INCIDENT-ANALYSIS-SYSTEM-AWS",
        ),
        candidate(
            "PratikSarkar25",
            "LLM-Powered-Intelligent-Log-Analysis-Anomaly-Detection",
        ),
        candidate("thiru0-0", "loglens"),
        candidate("pranayb1256", "NeuralOpsAI-"),
    ],
    41: [
        candidate("jgera", "Network-Intrusion-Detection-System"),
        candidate("vicky60629", "Network-Intrusion-Detection-System"),
        candidate("hectorpadin1", "Network-Intrusion-Detection-System"),
        candidate("OISF", "suricata"),
        candidate(
            "notsodubeyous",
            "IoT-Network-Intrusion-Detection-System-UNSW-NB15",
        ),
        candidate(
            "Colorado-Mesa-University-Cybersecurity",
            "DeepLearning-IDS",
        ),
        candidate("ymirsky", "Kitsune-py"),
        candidate(
            "rahulvigneswaran",
            "Intrusion-Detection-Systems",
        ),
    ],
    42: [
        candidate(
            "MaitreeVaria",
            "Indian-Sign-Language-Detection",
        ),
        candidate(
            "Diksha942",
            "Indian-Sign-Language-Detection",
        ),
        candidate(
            "PiyushBL45t",
            "Indian-Sign-Language-Detection-using-Deep-Learning",
        ),
        candidate(
            "PranavAngrish",
            "DynamicIndianSignLanguageDetection",
        ),
        candidate(
            "Tanwar-12",
            "Indian_Sign_Language_Detection-Yolov5",
        ),
        candidate(
            "AyushSingh2002",
            "Indian-Sign-Language-Detection",
        ),
        candidate(
            "ramasamy-24-t",
            "Indian-Sign-Language-Detection",
        ),
        candidate(
            "calicartels",
            "Indian-Sign-Language-Detection",
        ),
        candidate(
            "fyzanahammad",
            "Life-Saving-Signs-Real-Time-Detection-of-Emergency-Indian-Sign-Language",
        ),
        candidate(
            "PawarMukesh",
            "IndianSign-Language-Detector",
        ),
    ],
    43: [
        candidate("vardanagarwal", "Proctoring-AI"),
        candidate(
            "narender-rk10",
            "MyProctor.ai-AI-BASED-SMART-ONLINE-EXAMINATION-PROCTORING-SYSYTEM",
        ),
        candidate(
            "Hiteshydv001",
            "Guard-AI-Designing-Remote-Proctoring-System",
        ),
        candidate("shreyaspj20", "Reliable-proctoring-AI"),
        candidate("sanket2000", "proctoring"),
        candidate(
            "krishnakumaragrawal",
            "Artificial-Intelligence-based-Online-Exam-Proctoring-System",
        ),
        candidate("cegit27", "moodle-proctor"),
        candidate("hemantkarekar", "MyProctorAI"),
        candidate("mananmadan", "Unsupervised-Test"),
        candidate("reneverland", "CBIT-AiExam-plus"),
    ],
    84: [],
}