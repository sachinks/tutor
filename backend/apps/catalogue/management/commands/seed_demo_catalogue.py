"""Demo content: the 'AI Foundations' course (DEMO_DESIGN.md §8) with 3 published lessons, skills and a programme.
Safe to run many times. For development and demos only — real content goes through the content studio."""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.catalogue.models import (
    ClassLevel,
    Course,
    Lesson,
    LessonSkill,
    Module,
    Programme,
    ProgrammeCourse,
    PublishStatus,
    Skill,
    SkillPrerequisite,
    Subject,
)
from apps.assessment import services as assessment_services
from apps.assessment.models import Question, QuestionVersion
from apps.content import services as content_services
from apps.content.models import ContentVersion

SKILLS = [
    ("AI-DATA-01", "Tell features from labels in a dataset", []),
    ("AI-ML-01", "Explain the difference between training and prediction", ["AI-DATA-01"]),
    ("AI-ML-02", "Describe how a model finds patterns from examples", ["AI-DATA-01"]),
    ("AI-EVAL-01", "Measure a model with accuracy on test data", ["AI-ML-01", "AI-ML-02"]),
]

LESSONS = [
    ("what-is-data", "What is data?", 10, ["AI-DATA-01"], [
        ("Data is recorded observations",
         "Every time you write down a measurement — the height of a plant, the price of a cricket bat, "
         "the score in a match — you create **data**. A table of such records is called a **dataset**."),
        ("Features and labels",
         "In a dataset about fruits, *colour*, *weight* and *shape* are **features**: things we can observe. "
         "The fruit's name (apple, banana) is the **label**: the answer we want a machine to learn to give."),
        ("Try it",
         "Look at a cricket scorecard. Which columns would be features if we wanted to predict whether a team wins? "
         "What would the label be?"),
    ]),
    ("learning-from-examples", "Learning from examples", 12, ["AI-ML-01", "AI-ML-02"], [
        ("Training",
         "A machine learns by looking at many **examples** where both the features and the label are known. "
         "This stage is called **training**."),
        ("Finding patterns",
         "During training the model looks for patterns, such as *heavier yellow fruits are usually bananas*. "
         "It does not memorise every example; it builds a rule that works for most of them."),
        ("Prediction",
         "After training, we give the model only the features of a **new** fruit, and it predicts the label. "
         "This is **prediction** (also called inference)."),
    ]),
    ("is-the-model-any-good", "Is the model any good?", 12, ["AI-EVAL-01", "AI-ML-02"], [
        ("Keep some examples aside",
         "To test a model fairly we hide some examples during training. These are the **test data**."),
        ("Accuracy",
         "**Accuracy** = correct predictions ÷ total predictions. If the model gets 45 of 50 test fruits right, "
         "its accuracy is 45/50 = 90%."),
        ("Why test data matters",
         "Testing on the same examples used for training is like marking your own homework with the answer key "
         "you studied from: the score looks great but tells you little."),
    ]),
]

QUESTIONS = {
    "what-is-data": [
        ("AI-DATA-01", "A dataset lists fruits with colour, weight and name. Which column is the label?",
         ["Colour", "Weight", "Name", "All three"], 2,
         "The label is the answer we want the machine to predict: the fruit's name.",
         ["The label is what we want to predict.", "Colour and weight are things we observe."],
         {"0": "Colour is observed about the fruit, so it's a feature.", "3": "Only the answer to predict is the label."}),
        ("AI-DATA-01", "Which of these is a feature in a dataset about cricket matches?",
         ["Runs scored in the powerplay", "Who won the match", "The stadium's name only as a title", "None"], 0,
         "Runs in the powerplay are observed and could help predict the winner.",
         ["Features are observations; the result is usually the label."], {"1": "Who won is the label here."}),
        ("AI-DATA-01", "What is a dataset?",
         ["A single number", "A table of recorded observations", "A computer program", "A type of graph"], 1,
         "A dataset is a collection of records, usually arranged as a table.", ["Think of a scorecard with many rows."], {}),
    ],
    "learning-from-examples": [
        ("AI-ML-01", "What happens during training?",
         ["The model predicts new labels", "The model learns from examples with known labels",
          "We delete the data", "We choose the colour of the app"], 1,
         "Training uses examples where the answer (label) is already known.", ["Known answers are used here."],
         {"0": "Predicting new labels happens after training."}),
        ("AI-ML-01", "A trained model is shown a new fruit's colour and weight. What is it doing?",
         ["Training", "Prediction", "Labelling by hand", "Collecting data"], 1,
         "Using a trained model on new features is prediction (inference).", ["The model is not learning now."], {}),
        ("AI-ML-02", "How does a model 'learn' from examples?",
         ["It memorises every example exactly", "It finds patterns that work for most examples",
          "It asks the teacher", "It guesses randomly"], 1,
         "A model builds a rule from patterns so it also works on examples it has not seen.",
         ["Would memorising help with a fruit it has never seen?"], {"0": "Memorising fails on new examples."}),
    ],
    "is-the-model-any-good": [
        ("AI-EVAL-01", "A model gets 45 of 50 test examples right. What is its accuracy?",
         ["45%", "50%", "90%", "95%"], 2, "45 ÷ 50 = 0.9 = 90%.", ["Divide correct by total.", "Then turn it into a percentage."],
         {"0": "45 is the number correct, not the percentage."}),
        ("AI-EVAL-01", "Why do we keep test data separate from training data?",
         ["To save storage", "To check the model on examples it hasn't seen", "Because it is wrong data", "No reason"], 1,
         "Testing on unseen examples shows how the model will do in real use.",
         ["Think of marking homework with the answers you studied."], {}),
        ("AI-ML-02", "A model scores 100% on its training data but 55% on test data. What does that suggest?",
         ["It is perfect", "It memorised the training data instead of learning patterns", "The test is broken", "Nothing"], 1,
         "A big gap means it didn't learn patterns that generalise.", ["Compare the two scores."], {"0": "100% only on seen data is not real skill."}),
    ],
}


def _system_user(email, name):
    user, created = User.objects.get_or_create(
        email=email, defaults={"full_name": name, "account_type": "staff", "is_staff": False}
    )
    if created:
        user.set_unusable_password()
        user.save()
    return user


class Command(BaseCommand):
    help = "Create the demo 'AI Foundations' course with published lessons, skills and a programme."

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_reference", verbosity=0)
        author = _system_user("demo-author@tutor.local", "Demo Author")
        reviewer = _system_user("demo-reviewer@tutor.local", "Demo Reviewer")
        subject = Subject.objects.get(slug="ai-foundations")

        skills = {}
        for code, name, _ in SKILLS:
            skills[code], _ = Skill.objects.update_or_create(code=code, defaults={"name": name, "subject": subject})
        for code, _, requires in SKILLS:
            for req in requires:
                SkillPrerequisite.objects.get_or_create(skill=skills[code], requires=skills[req])

        course, _ = Course.objects.update_or_create(
            slug="ai-foundations",
            defaults={
                "title": "AI Foundations", "subject": subject, "class_level": None,
                "summary": "How machines learn from data, in plain language, with hands-on thinking tasks.",
                "track": Course.Track.AI_IN_SUBJECT, "path_stage": 2, "price_paise": 49900,
                "status": PublishStatus.PUBLISHED,
            },
        )
        module, _ = Module.objects.update_or_create(course=course, position=1, defaults={"title": "How machines learn"})
        course.free_module = module
        course.save(update_fields=["free_module"])

        for position, (slug, title, minutes, skill_codes, sections) in enumerate(LESSONS, start=1):
            lesson, _ = Lesson.objects.update_or_create(
                module=module, position=position, defaults={"slug": slug, "title": title, "est_minutes": minutes}
            )
            for code in skill_codes:
                LessonSkill.objects.get_or_create(lesson=lesson, skill=skills[code])
            if not content_services.published_version(lesson):
                version = ContentVersion.objects.create(
                    lesson=lesson, version_no=content_services.next_version_no(lesson),
                    body={"sections": [{"heading": h, "blocks": [{"type": "text", "text": t}]} for h, t in sections]},
                    status=ContentVersion.Status.APPROVED, author=author, reviewer=reviewer,
                )
                content_services.publish(version, reviewer)

        for lesson in Lesson.objects.filter(module=module):
            for position, (code, stem, choices, answer, explanation, hints, misconceptions) in enumerate(
                QUESTIONS.get(lesson.slug, []), start=1
            ):
                question, _ = Question.objects.get_or_create(
                    lesson=lesson, position=position, purpose=Question.Purpose.QUIZ,
                    defaults={"skill": skills[code], "type": Question.Type.MCQ},
                )
                if not assessment_services.published_question_version(question):
                    qv = QuestionVersion.objects.create(
                        question=question, version_no=assessment_services.next_question_version_no(question),
                        body={"stem": stem, "options": choices, "answer_index": answer, "explanation": explanation,
                              "hints": hints, "misconceptions": misconceptions},
                        status=QuestionVersion.Status.APPROVED, author=author, reviewer=reviewer,
                    )
                    assessment_services.publish_question_version(qv, reviewer)

        programme, _ = Programme.objects.update_or_create(
            slug="explore-ai-class-8",
            defaults={
                "title": "Explore AI (Class 8)", "path_stage": 2, "price_paise": 79900,
                "class_level": ClassLevel.objects.get(number=8), "status": PublishStatus.PUBLISHED,
                "summary": "Start with AI Foundations; more AI + Core courses are added as they are published.",
            },
        )
        ProgrammeCourse.objects.get_or_create(programme=programme, course=course, defaults={"position": 1})

        if options.get("verbosity", 1) > 0:
            self.stdout.write(self.style.SUCCESS(
                f"Demo catalogue ready: course '{course.title}' with {module.lessons.count()} lessons, "
                f"{len(skills)} skills, programme '{programme.title}'."
            ))
