"""Keyword lists, patterns and lookup tables for the email classifier.
ATS_DOMAINS, ATS_RULES and KNOWN_PLATFORMS overlap on purpose: they answer "is this an ATS?",
"how do we find the employer behind this ATS?" and "is this domain not the employer?"."""

import re


BLOCKED_SENDER_DOMAINS = {
    "rekomendacje@",
    "newsletter",
    "job-alert",
    "job_alert",
    "jobalert",
    "alert@",
    "digest@",
    "recommendations@",
    "no-reply@indeed",
    "alert@indeed",
    "jobs2web.com",
    "jobnotification@",
    "talent-alert",
    "talentbrew",
    "jobscore",
    "job-notification",
    "career-alert",
    "jobalerts",
    "justjoin.it",
    "twine.net",
    "twine.com",
    "no-reply@justjoin.it",
    "newsletter@twine",
    "googlewallet-noreply@google.com",
    "google-wallet",
    "noreply@google.com",
    "accounts-noreply@google.com",
    "your payment was unsuccessful",
    "payment confirmation",
    "your order",
    "your receipt",
    "invoice from",
    "subscription renewal",
    "security alert",
    "sign-in attempt",
    "verify your email address",
    "confirm your email",
    "password reset",
    "two-factor",
    "2-step verification",
    "account recovery",
    "storage almost full",
    "google storage",
}

BLOCKED_SUBJECT_KEYWORDS = {
    "oferta",
    "oferty",
    "job alert",
    "jobs you may like",
    "recommended jobs",
    "new jobs for you",
    "job recommendations",
    "jobs matching",
    "interesting jobs",
    "career opportunities for you",
    "open positions near",
    "new opportunities for you",
    "jobs near you",
    "top jobs for you",
    "% match:",
    "% match ",
    "job opportunities posted",
    "new job opportunities",
    "jobs for you",
    "your payment was unsuccessful",
    "contactless payment",
    "hold your phone near the reader",
    "unsubscribe from our",
    "this is a marketing email",
    "you are receiving this email because you",
    "manage your preferences",
    "view in browser",
    "jobs you may like",
    "recommended for you",
    "new jobs for you",
    "jobs matching your",
    "your job alert",
    "people are viewing",
    "your profile appeared",
    "who viewed your profile",
    "linkedin weekly",
    "linkedin news",
    "add connections",
    "people you may know",
    "apply now",
    "your application was viewed",
    "application was viewed by",
    "reset your password",
    "welcome to",
    "verify your candidate account",
    "sign in and continue your application",
    "career site account",
    "pracodawca zapoznał się z twoją aplikacją",
    "zapoznał się z twoją aplikacją",
}

JOB_SIGNALS_SUBJECT = {
    "application", "applied", "applying", "thank you for your",
    "we received your", "your candidacy", "interview", "offer",
    "assessment", "hiring", "position", "vacancy", "job",
    "candidate", "recruitment", "role", "opportunity",
    "next steps", "moving forward", "not moving forward",
    "unfortunately", "regret to inform", "not selected",
    "aplikacja", "aplikacji", "rekrutacja", "rekrutacyjn",
    "dziękujemy", "kandydatura", "oferta pracy",
    "zaproszenie", "zgłoszenie", "stanowisko",
    "pracodawca", "twoja aplikacja", "logic challenge",
    "graduate challenge", "engineer", "developer", "analyst", "specialist",
    "scientist", "programista", "inżynier", "analityk",
}

# Words in a subject that point to the user's own application process.
# The Polish "aplikacja" is left out: it also means a mobile app.
APPLICATION_SUBJECT_WORDS = re.compile(
    r"\b(?:interview|application|applied|applying|candidacy|recruitment|recruiting|"
    r"assessment|rekrutac\w*|rozmow\w* kwalifikacyjn\w*)\b",
    re.IGNORECASE,
)

JOB_SIGNALS_BODY = {
    "applied for", "your application", "thank you for applying",
    "we received your application", "interview", "offer of employment",
    "job offer", "not moving forward", "decided to pursue",
    "other candidates", "your candidacy", "hiring team",
    "recruitment team", "talent acquisition", "recruiter",
    "twoja aplikacja", "dziękujemy za", "aplikacji na",
    "proces rekrutacji", "kandydatury", "zgłoszenie",
    "stanowisko", "rekrutacyjnego",
}

BLOCKED_BODY_PATTERNS = {
    "unsubscribe from job alerts",
    "you are receiving this because you set up a job alert",
    "update your job alert preferences",
    "manage your job alerts",
    "you subscribed to",
    "to stop receiving these emails",
    "this is an automated job recommendation",
    "pracodawca zapoznał się z twoją aplikacją",
    "porównuje kompetencje",
}

# Applicant tracking systems: they send mail on behalf of the employer.
ATS_DOMAINS = {
    "myworkday.com", "myworkdayjobs.com", "workday.com",
    "icims.com", "workable.com", "workablemail.com", "erecruiter.pl",
    "traffit.com", "traffit-mail.com", "traffit-ms.com", "recruitee.com",
    "smartrecruiters.com", "greenhouse.io", "greenhouse-mail.io", "lever.co",
    "ashbyhq.com", "successfactors.com", "successfactors.eu", "sapsf.com", "sapsf.eu",
    "pinpointhq.com", "peopleforce.io", "avature.net", "jobvite.com",
    "teamtailor.com", "teamtailor-mail.com", "personio.com", "personio.de",
    "bamboohr.com", "breezy.hr", "comeet.com", "comeet.co", "join.com",
    "dover.com", "jazz.co", "jazzhr.com", "rippling.com", "taleo.net",
    "ultipro.com", "kronos.com", "recruiterbox.com",
}

# Assessment platforms — always job related
ASSESSMENT_PLATFORMS = {
    "hackerrank.com", "codesignal.com", "codility.com", "testgorilla.com",
    "vervoe.com", "pymetrics.com", "hirevue.com", "mercer.com", "shl.com",
    "coderbyte.com", "qualified.io", "filtered.ai",
}

JOB_BOARD_DOMAINS = {
    "linkedin.com", "indeed.com", "pracuj.pl", "justjoin.it", "glassdoor.com",
    "monster.com", "stepstone.de", "bayt.com", "nofluffjobs.com", "twinehq.com",
    "jobs2web.com", "bulldogjob.pl", "rocketjobs.pl", "theprotocol.it",
}

# A sender on one of these is never the employer itself.
PLATFORM_DOMAINS = ATS_DOMAINS | ASSESSMENT_PLATFORMS | JOB_BOARD_DOMAINS

# Personal mail providers: the domain says nothing about the employer.
PERSONAL_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "live.com", "icloud.com", "wp.pl", "o2.pl", "onet.pl", "interia.pl",
}

# Names of the platforms above. A company with one of these names is a platform, not an employer.
PLATFORM_NAMES = {
    "workday", "myworkday", "icims", "workable", "workablemail", "erecruiter",
    "traffit", "recruitee", "smartrecruiters", "greenhouse", "greenhousemail",
    "lever", "ashby", "ashbyhq", "successfactors", "sapsuccessfactors", "pinpoint",
    "pinpointhq", "peopleforce", "avature", "jobvite", "teamtailor", "personio",
    "bamboohr", "breezy", "breezyhr", "comeet", "dover", "jazz", "jazzhr",
    "rippling", "taleo", "ultipro", "kronos", "recruiterbox", "join", "joincom",
    "hackerrank", "codility", "codesignal", "testgorilla", "hirevue", "linkedin",
    "indeed", "pracuj", "pracujpl", "justjoin", "justjoinit", "nofluffjobs", "glassdoor",
}

# ATS platforms that put the employer in the sender's subdomain (brightwave.greenhouse.io).
ATS_SUBDOMAIN_RULES = {
    "greenhouse.io", "workday.com", "myworkdayjobs.com", "ashbyhq.com",
    "teamtailor.com", "recruitee.com", "bamboohr.com", "icims.com",
}

STRONG_REJECTION_PATTERNS: list[str] = [
    r"regret to inform",
    r"(?:have|need|must) to inform you that",
    r"unfortunately,? (?:we|i) (?:are unable|cannot|can't|won't|will not|are not able) (?:to )?(?:offer|proceed|move forward|progress|continue|take your application)",
    r"unfortunately,? (?:we|i) (?:have|'ve) decided (?:not|to (?:move|proceed|go) forward with (?:other|another))",
    r"not (?:be )?moving forward with (?:your|you)",
    r"(?:decided|chosen|elected) (?:not )?to (?:move|proceed|go|continue) (?:forward |ahead )?with (?:other|another|a different)",
    r"(?:move|moving|proceed|proceeding) forward with other (?:candidates|applicants)",
    r"(?:will not|won't) be (?:moving forward|proceeding|progressing|taking (?:your|this))",
    r"not be proceeding",
    r"(?:have|has) not been (?:selected|successful|shortlisted)",
    r"(?:were|was|are|is) not (?:selected|successful|shortlisted)",
    r"position has (?:now )?been filled",
    r"(?:unable|not able) to offer you",
    r"(?:we have|we've) decided not to",
    r"decided not to (?:move|proceed|go) (?:forward |ahead )?with your",
    r"not (?:to )?progress(?:ing)? (?:with )?your (?:application|candidacy)",
    r"no longer (?:being )?considered",
    r"(?:application|candidacy) (?:was|has been|is) unsuccessful",
    r"decided to pursue other candidates",
    r"not take your application further",
    r"tym razem wybrali(?:śmy|smy)",
    r"wybrali(?:śmy|smy) (?:inn|kandydat)",
    r"zdecydowali(?:śmy|smy) się (?:na |wybrać )?inn",
    r"zdecydowali(?:śmy|smy) się kontynuować (?:proces |rekrutację )?z inn",
    r"nie możemy (?:ci |pani |panu |państwu )?zaproponować",
    r"nie zakwalifikował(?:a|e)?(?:ś|s)? się",
    r"nie zakwalifikowali",
    r"nie przeszedł(?:e|a)?(?:ś|s)?\b",
    r"nie przeszła(?:ś)?\b",
    r"nie będziemy kontynuować",
    r"postanowili(?:śmy|smy) nie kontynuować",
    r"kandydatura nie (?:została|zostanie)",
    r"z przykrością (?:informujemy|musimy)",
]

WEAK_REJECTION_PATTERNS: list[str] = [
    r"\bunfortunately\b",
    r"other candidates",
    r"(?:we've|we have) decided",
    r"after careful (?:consideration|review)",
    r"\bunsuccessful\b",
    r"decision has been made",
    r"\bniestety\b",
    r"inn(?:e|ych) kandydat",
]

# Phrases that usually end a process; a rejection only when the email also says so.
PROCESS_END_PATTERNS: list[str] = [
    r"dziękujemy za udział w (?:procesie|rekrutacji)",
    r"thank you for (?:taking part|participating) in (?:the |our )?(?:recruitment|selection|interview|hiring) process",
]

CONFIRMATION_PATTERNS: list[str] = [
    r"thank you for (?:applying|your application|submitting|your interest in)",
    r"thanks for (?:applying|submitting|your application)",
    r"we (?:have )?received your (?:application|cv|resume)",
    r"(?:application|cv|resume) (?:has been |was )?(?:received|submitted|confirmed|acknowledged)",
    r"successfully (?:applied|submitted)",
    r"application confirmation",
    r"we(?:'ll| will) (?:review|be reviewing) your (?:application|profile|cv)",
    r"thank you for expressing (?:your )?interest in (?:this|the|our) (?:opportunity|position|role|vacancy)",
    r"your (?:information|application|profile|details|cv|resume) will be (?:shared with|forwarded to|passed on to|reviewed by) (?:the |our )?(?:appropriate |relevant |hiring )?(?:recruiter|recruiting team|hiring team|hiring manager|team)",
    r"we have successfully received",
    r"your application (?:has been|was) (?:sent|submitted|delivered|successfully submitted)",
    r"we appreciate your interest in (?:joining|working|the|this|our)",
    r"dziękujemy za (?:twoją |pani |pana )?(?:złożenie |przesłanie |wysłanie )?(?:aplikacj|zgłoszeni|cv|kandydatur)",
    r"otrzymali(?:śmy|smy) (?:twoją |pani |pana )?(?:aplikacj|zgłoszeni|cv)",
    r"aplikacja została (?:przyjęta|wysłana|złożona|zarejestrowana)",
    r"zgłoszenie zostało (?:przyjęte|wysłane|zarejestrowane|złożone)",
    r"dziękujemy za przesłanie",
]

# An offer has to be made to the candidate; "what we offer" and "I got an offer" don't count.
OFFER_PATTERNS: list[str] = [
    r"(?:we are|we're|i am|i'm) (?:pleased|happy|delighted|excited|thrilled) to (?:offer you|extend (?:you )?(?:an? )?(?:formal )?offer)",
    r"offer of employment",
    r"\boffer letter\b",
    r"(?:pleased|happy|delighted) to (?:make|extend) you an offer",
    r"your (?:formal |official |written |job )?offer (?:letter|details|package|is attached)",
    r"(?:accept|sign) (?:the|your|this) offer",
]

INTERVIEW_PATTERNS: list[str] = [
    r"interview invitation",
    r"invit(?:e|ation|ing) you (?:to|for) (?:an? |the )?(?:\w+ )?interview",
    r"schedule (?:an? |your |the )?(?:\w+ )?interview",
    r"interview (?:scheduled|confirmed)",
    r"(?:your|an|the) interview (?:is |has been |will be )?(?:scheduled |confirmed |booked |set )?(?:on|at|for) \w",
    r"phone (?:screen|call|interview)",
    r"video (?:call|interview)",
    r"technical interview",
    r"virtual interview",
    r"meet with (?:our|the) team",
    r"calendly\.com",
    r"book(?:ing)? a (?:time|slot|call)",
    r"chcieli(?:byśmy|bysmy) zaprosić",
    r"zaprasza(?:my|m) na (?:rozmowę|spotkanie)",
    r"umówić (?:się na )?rozmowę",
    r"would like to (?:schedule|invite you)",
    r"next (?:step|round) (?:is|will be) an? interview",
    r"interview reminder",
]

# Questions about the process rather than its outcome: never a status on their own.
FEEDBACK_PATTERNS: list[str] = [
    r"(?:share|give|provide|leave) (?:us )?(?:your |some )?(?:feedback|opinion|thoughts)",
    r"candidate (?:experience|survey|satisfaction|feedback)",
    r"interview feedback",
    r"(?:short|brief|quick) (?:survey|questionnaire)",
    r"how (?:was|did) (?:your|the) (?:interview|experience|recruitment)",
    r"rate your (?:experience|interview)",
]

ASSESSMENT_PATTERNS: list[str] = [
    r"invitation to (?:the |an |our )?(?:online )?assessment",
    r"online (?:test|assessment)",
    r"coding (?:test|challenge|assessment|exercise|task)",
    r"take[- ]home (?:test|task|assignment|challenge|exercise)",
    r"technical (?:test|assessment|task|exercise|challenge)",
    r"(?:complete|take) (?:a|the|an|our) (?:short )?(?:online )?(?:test|assessment|task|challenge|questionnaire)",
    r"assessment (?:link|invitation|invite)",
    r"homework (?:assignment|task)",
    r"code challenge",
    r"\b(?:hackerrank|codility|codesignal|testgorilla|hirevue)\b",
    r"(?:skills?|aptitude|psychometric|logic|cognitive|personality) (?:test|assessment)",
    r"graduate logic challenge",
    r"zadani(?:e|a|em) rekrutacyjn",
    r"zadanie domowe",
    r"test (?:online|kompetencji|wiedzy|umiejętności|techniczny)",
    r"zaprosz\w* do (?:testu|zadania|rozwiązania)",
]

# A sentence with one of these words talks about what might happen, not what did.
CONDITIONAL_WORDS = re.compile(
    r"\b(?:if|should|in case|in the event|unless|whether|may|might|jeśli|jeżeli|w przypadku|gdyby|o ile|w razie)\b"
    r"|\b(?:selected|shortlisted|successful|suitable) (?:candidates|applicants) (?:will|may|are)\b",
    re.IGNORECASE,
)

# Job alerts and recommendations: they name companies and roles but are never applications.
JOB_ALERT_SUBJECT_PATTERNS: list[str] = [
    r"\bis hiring\b",
    r"\bare hiring\b",
    r"recommendations? based on your",
    r"expand your (?:job )?search",
    r"jobs? (?:you may be|you might be|that may be) interested",
    r"\b(?:new )?jobs similar to\b",
    r"\bapply now to\b",
    r"you may be a fit",
    r"\bjob alert",
    r"\bjobs? for you\b",
    r"recommended (?:jobs|for you|roles|offers)",
    r"\bnew (?:job )?offers?\b",
    r"\bnowe oferty\b",
    r"\boferty pracy dla\b",
    r"\bdopasowane oferty\b",
    r"\b\d+\+? new jobs?\b",
    r"\bnew jobs? (?:in|at|for|matching)\b",
    r"\bjobs? matching\b",
    r"\btop jobs\b",
    r"\bsimilar jobs\b",
    r"\bjobs? near you\b",
    r"\bwho'?s hiring\b",
]

# Senders that only ever send job alerts.
JOB_ALERT_SENDER_DOMAINS = {"match.indeed.com"}
# Words in a sender's name that mark a community digest or newsletter.
SOCIAL_SENDER_NAME_WORDS = re.compile(r"\b(?:community|newsletter|digest|awards)\b", re.IGNORECASE)
SOCIAL_SUBJECT = re.compile(
    r"\b(?:weekly|daily|monthly) (?:digest|roundup|newsletter)\b|\bnewsletter\b|\bpodsumowanie twoich aplikacji\b",
    re.IGNORECASE,
)

LINKEDIN_JOB_ALERT_SENDERS = {"jobalerts-noreply@linkedin.com"}
# Recruiter conversations on LinkedIn: kept as Needs Review even without a company.
LINKEDIN_CONVERSATION_SENDERS = {"hit-reply@linkedin.com", "inmail-hit-reply@linkedin.com"}
LINKEDIN_SOCIAL_SENDERS = {
    "invitations@linkedin.com", "notifications-noreply@linkedin.com", "groups-noreply@linkedin.com",
    "editors-noreply@linkedin.com", "updates-noreply@linkedin.com", "member@linkedin.com",
    "news@linkedin.com", "messages-noreply@linkedin.com", "messaging-digest-noreply@linkedin.com",
}
# Social networks and newsletters: they talk about jobs, but not about the user's applications.
SOCIAL_SENDER_DOMAINS = {
    "em.linkedin.com", "e.linkedin.com", "redditmail.com", "facebookmail.com", "substack.com",
    "medium.com", "quora.com", "x.com", "twitter.com", "instagram.com", "youtube.com",
    "discord.com", "indiehackers.com", "github.com", "producthunt.com", "meetup.com",
    "leetcode.com", "datacamp.com", "coursera.org", "udemy.com", "edx.org",
}

ROLE_PATTERNS: list[str] = [
    r"for the (?:role|position) of\s+(?:an?\s+)?(?P<role>.+)",
    r"(?:role|position) of\s+(?:an?\s+)?(?P<role>.+)",
    r"(?:for|to) the\s+(?P<role>.+?)\s+(?:position|role|vacancy|opening|job)\b",
    r"(?:application|candidacy) for\s+(?:the\s+)?(?:position of\s+)?(?P<role>.+)",
    r"(?:applied|applying) for\s+(?:the\s+)?(?:position of\s+)?(?P<role>.+)",
    r"na stanowisko\s+(?P<role>.+)",
    r"(?:position|role|job title|stanowisko)\s*:\s*(?P<role>.+)",
    r"\bas an?\s+(?P<role>.+)",
    r"^(?P<role>.+?)\s+(?:at|@)\s+\S",
    r"^(?P<role>.+?)\s+[-–—|]\s+[^-–—|]+$",
]

DISPLAY_NAME_NOISE = {
    "hiring", "team", "talent", "acquisition", "recruitment", "recruiting",
    "careers", "career", "hr", "human", "resources", "noreply", "no-reply",
    "notifications", "notification", "jobs", "job", "apply", "group", "global",
    "emea", "international", "services", "donotreply", "do-not-reply", "hire",
    "workday", "administrator", "admin", "icims", "wd", "via", "people", "system",
    "mailer", "automated", "portal", "applicant", "candidate", "candidates", "the",
}

ROLE_NOISE = {
    "unknown", "logic challenge", "graduate programme", "tech talent programme",
    "it careers", "hiring team", "talent acquisition", "graduate logic challenge",
    "coding challenge", "technical challenge", "online assessment", "take home",
    "take-home", "coding test", "technical test", "hackerrank", "codility",
    "codesignal", "testgorilla", "assessment", "challenge", "programme",
}
ROLE_NOISE.update({
    "junior", "senior", "lead", "principal", "staff",
    "associate", "regular", "mid", "medior",
    "position", "a position", "the position", "this position",
    "role", "a role", "the role",
    "opportunity", "career opportunity", "vacancy", "opening",
    "application", "job application", "candidate",
    "interest in the", "i your application", "your application",
})

VALID_ROLE_KEYWORDS = {
    "engineer", "developer", "scientist", "analyst", "manager",
    "architect", "consultant", "specialist", "administrator",
    "technician", "designer", "researcher", "officer", "director",
    "coordinator", "devops", "sre", "qa", "tester", "product",
    "security", "cybersecurity", "data", "backend", "frontend",
    "full stack", "fullstack", "software", "cloud", "platform",
    "machine learning", "ai", "intern", "graduate", "trainee",
    "student", "programmer", "accountant", "recruiter", "assistant",
    "advisor", "representative", "lead", "marketing", "sales", "support",
    "operations", "writer", "editor", "controller", "auditor", "lawyer",
    "programista", "inżynier", "analityk", "specjalista", "stażysta", "praktykant",
}

# Used to tell a recruiter's personal display name ("Anna Kowalska") from a company name.
# Names that are also common words or brand names (Grace, Mark, Rose, ...) are left out on purpose.
_ENGLISH_FEMALE_NAMES = {
    "mary", "patricia", "jennifer", "linda", "elizabeth", "barbara", "susan", "jessica",
    "sarah", "karen", "lisa", "nancy", "betty", "sandra", "margaret", "ashley",
    "kimberly", "emily", "donna", "michelle", "carol", "amanda", "melissa", "deborah",
    "stephanie", "rebecca", "sharon", "laura", "cynthia", "amy", "kathleen", "angela",
    "shirley", "emma", "brenda", "pamela", "nicole", "anna", "samantha", "katherine",
    "christine", "debra", "rachel", "carolyn", "janet", "maria", "olivia", "heather",
    "helen", "catherine", "diane", "julie", "victoria", "lauren", "kelly", "christina",
    "joan", "evelyn", "judith", "megan", "hannah", "andrea", "cheryl", "jacqueline",
    "martha", "madison", "teresa", "gloria", "sara", "janice", "ann", "kathryn",
    "abigail", "sophia", "frances", "jean", "alice", "judy", "isabella", "julia",
    "denise", "danielle", "marilyn", "beverly", "charlotte", "natalie", "theresa", "diana",
    "brittany", "doris", "kayla", "alexis", "chloe", "sophie", "lucy", "ella",
    "mia", "amelia", "jane", "claire", "zoe", "ruth",
}
_ENGLISH_MALE_NAMES = {
    "james", "robert", "john", "michael", "david", "william", "richard", "joseph",
    "thomas", "christopher", "charles", "daniel", "matthew", "anthony", "donald", "steven",
    "andrew", "paul", "joshua", "kenneth", "kevin", "brian", "george", "timothy",
    "ronald", "jason", "edward", "jeffrey", "ryan", "jacob", "gary", "nicholas",
    "eric", "jonathan", "stephen", "larry", "justin", "scott", "brandon", "benjamin",
    "samuel", "gregory", "alexander", "patrick", "frank", "raymond", "dennis", "jerry",
    "tyler", "aaron", "jose", "adam", "nathan", "henry", "zachary", "douglas",
    "peter", "kyle", "noah", "ethan", "jeremy", "walter", "keith",
    "roger", "terry", "austin", "sean", "gerald", "carl", "harold", "dylan",
    "arthur", "lawrence", "jordan", "jesse", "bryan", "bruce", "gabriel", "logan",
    "alan", "juan", "albert", "elijah", "wayne", "vincent", "liam", "oliver",
    "harry", "luke", "oscar", "tom", "chris", "mike", "ben", "sam",
}
# Polish names with diacritics are listed both with and without them, since
# display names often drop them ("Malgorzata").
_POLISH_FEMALE_NAMES = {
    "anna", "maria", "katarzyna", "małgorzata", "malgorzata", "agnieszka", "barbara", "ewa",
    "krystyna", "magdalena", "elżbieta", "elzbieta", "joanna", "aleksandra", "monika", "zofia",
    "teresa", "danuta", "natalia", "julia", "karolina", "marta", "beata", "dorota",
    "halina", "jadwiga", "jolanta", "iwona", "grażyna", "grazyna", "paulina", "justyna",
    "bożena", "bozena", "urszula", "alicja", "agata", "renata", "sylwia", "hanna",
    "wiktoria", "irena", "helena", "patrycja", "izabela", "emilia", "weronika", "dominika",
    "ewelina", "oliwia", "martyna", "gabriela", "kinga", "wioletta", "marianna", "kamila",
    "edyta", "janina", "lena", "maja", "zuzanna", "milena", "klaudia", "angelika",
    "adrianna", "kornelia", "marzena", "lucyna", "żaneta", "zaneta",
}
_POLISH_MALE_NAMES = {
    "piotr", "krzysztof", "andrzej", "tomasz", "paweł", "pawel", "jan", "michał",
    "michal", "marcin", "stanisław", "stanislaw", "jakub", "adam", "marek", "łukasz",
    "lukasz", "grzegorz", "mateusz", "wojciech", "mariusz", "dariusz", "zbigniew", "jerzy",
    "maciej", "rafał", "rafal", "robert", "kamil", "józef", "jozef", "janusz",
    "szymon", "kacper", "jacek", "sławomir", "slawomir", "dawid", "ryszard", "bartosz",
    "przemysław", "przemyslaw", "sebastian", "artur", "damian", "daniel", "patryk", "kazimierz",
    "filip", "karol", "mirosław", "miroslaw", "henryk", "roman", "wiktor", "igor",
    "antoni", "aleksander", "franciszek", "dominik", "hubert", "oskar", "adrian", "leszek",
    "marian", "tadeusz", "bogdan", "waldemar", "arkadiusz", "radosław", "radoslaw", "norbert",
    "konrad", "emil",
}
COMMON_FIRST_NAMES = (
    _ENGLISH_FEMALE_NAMES | _ENGLISH_MALE_NAMES | _POLISH_FEMALE_NAMES | _POLISH_MALE_NAMES
)

_ROLE_NOISE_PREFIXES = (
    "re:", "fw:", "fwd:", "your application", "thank you", "thanks for",
    "we received", "application received", "application confirmation",
)


COMPANY_OVERRIDES: dict[str, str] = {
    "samsung electronics": "Samsung",
    "google llc": "Google",
    "meta platforms": "Meta",
    "meta platforms inc": "Meta",
    "amazon web services": "AWS",
    "amazon web services emea sarl": "AWS",
    "ernst & young": "EY",
    "pricewaterhousecoopers": "PwC",
    "ey": "EY",
    "no reply": "Unknown",
}

INVALID_ROLES = {
    "it careers", "graduate programme", "tech talent programme",
    "logic challenge", "hiring team", "talent acquisition",
    "graduate logic challenge", "full", "unknown",
    "junior", "senior", "intern", "internship",
    "tech talent", "talent programme",
    "it careers", "back",
    "developer",
    "engineer",
}

ROLE_CANONICAL: dict[str, str] = {
    "software engineer": "Software Engineer",
    "software developer": "Software Developer",
    "frontend developer": "Frontend Developer",
    "frontend engineer": "Frontend Engineer",
    "back-end developer": "Backend Developer",
    "backend developer": "Backend Developer",
    "backend engineer": "Backend Engineer",
    "fullstack developer": "Full Stack Developer",
    "full stack developer": "Full Stack Developer",
    "full-stack developer": "Full Stack Developer",
    "java developer": "Java Developer",
    "java engineer": "Java Engineer",
    "python developer": "Python Developer",
    "python engineer": "Python Engineer",
    "data scientist": "Data Scientist",
    "data engineer": "Data Engineer",
    "devops engineer": "DevOps Engineer",
    "machine learning engineer": "Machine Learning Engineer",
    "product manager": "Product Manager",
    "project manager": "Project Manager",
    "ux designer": "UX Designer",
    "ui/ux designer": "UI/UX Designer",
    "qa engineer": "QA Engineer",
    "test engineer": "QA Engineer",
    "quality assurance engineer": "QA Engineer",
}

# Applied in order, anchored to end of string; loop until stable
COMPANY_SUFFIX_PATTERNS = [
    re.compile(
        r",?\s*\b(?:Poland|Germany|France|United Kingdom|UK|USA|United States|"
        r"Czech Republic|Romania|Hungary|Netherlands|Belgium|Sweden|Norway|"
        r"Denmark|Finland|Austria|Switzerland|Italy|Spain|Portugal|India|"
        r"China|Japan|Canada|Australia|Brazil)\b\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r",?\s*\b(?:R&D Institute|Research (?:and|&) Development|Research Institute|"
        r"Innovation (?:Center|Lab)|Technology Center)\b\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r",?\s*\b(?:International|Global|Group|Holdings?|Ventures?|Technologies?|"
        r"Tech|Solutions?|Services?|Systems?)\b\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r",?\s*\b(?:GmbH|LLC|Ltd\.?|Inc\.?|Corp\.?|S\.A\.|AG|BV|NV|SE|PLC|"
        r"S\.p\.A\.|S\.r\.l\.|SARL|SAS|Oy|AB|AS|ApS)(?!\w)\s*$",
        re.IGNORECASE,
    ),
    re.compile(r",?\s*[Ss]p\.\s*z\s*o\.\s*o?\.?\s*$"),
    re.compile(r",?\s*sp[oó]łka\s+z\s+ograniczon\w*\s+odpowiedzialno\w*\.?\s*$", re.IGNORECASE),
    re.compile(r",?\s*sp[oó]łka\s+akcyjna\s*$", re.IGNORECASE),
]

SENIORITY_PREFIX = re.compile(
    r"^(?:junior|senior|mid|lead|principal|regular|medior|intern|working student|werkstudent|"
    r"entry.level|sr\.?|jr\.?|staff|associate)\s+",
    re.IGNORECASE,
)
GENDER_MARKER = re.compile(
    r"\s*[\(\[]\s*(?:[mfwdx](?:[/|,][mfwdx])*)\s*[\)\]]",
    re.IGNORECASE,
)
# " - Team name", " | Location": only with spaces around, so "Full-Stack" stays whole.
LOCATION_SUFFIX = re.compile(r"\s+[-–—|]\s+.+$")

KNOWN_PLATFORMS = PLATFORM_DOMAINS | PERSONAL_MAIL_DOMAINS

SUBDOMAIN_PREFIXES_TO_SKIP = {
    "mail", "noreply", "no-reply", "donotreply", "do-not-reply",
    "careers", "jobs", "recruiting", "recruitment", "hr", "talent",
    "hiring", "apply", "applications", "notification", "notifications",
    "info", "hello", "team", "support", "contact",
}
