"""References and appendices."""

from __future__ import annotations

REFERENCES = [
    'Li, M., T. Lv, J. Chen, L. Cui, Y. Lu, D. Florencio, C. Zhang, Z. Li, and '
    'F. Wei, "TrOCR: Transformer-based Optical Character Recognition with '
    'Pre-trained Models," arXiv:2109.10282, 2021; AAAI 2023. '
    'https://arxiv.org/abs/2109.10282',

    'Marti, U.-V., and H. Bunke, "The IAM-database: an English sentence '
    'database for offline handwriting recognition," International Journal on '
    'Document Analysis and Recognition, Vol. 5, No. 1, pp. 39-46, 2002. '
    'DOI 10.1007/s100320200071',

    'Garrido-Munoz, C., and J. Calvo-Zaragoza, "On the Generalization of '
    'Handwritten Text Recognition Models," arXiv:2411.17332, 2024 (rev. 2025). '
    'https://arxiv.org/abs/2411.17332',

    'Garrido-Munoz, C., A. Rios-Vila, and J. Calvo-Zaragoza, "Handwritten Text '
    'Recognition: A Survey," arXiv:2502.08417, 2025. '
    'https://arxiv.org/abs/2502.08417',

    'Gongidi, S., and C. V. Jawahar, "iiit-indic-hw-words: A Dataset for Indic '
    'Handwritten Text Recognition," International Conference on Document '
    'Analysis and Recognition (ICDAR) 2021, LNCS, pp. 444-459. '
    'DOI 10.1007/978-3-030-86337-1_30',

    'Otsu, N., "A Threshold Selection Method from Gray-Level Histograms," IEEE '
    'Transactions on Systems, Man, and Cybernetics, Vol. 9, No. 1, pp. 62-66, '
    '1979. DOI 10.1109/TSMC.1979.4310076',

    'Sauvola, J., and M. Pietikainen, "Adaptive document image binarization," '
    'Pattern Recognition, Vol. 33, No. 2, pp. 225-236, 2000. '
    'DOI 10.1016/S0031-3203(99)00055-2',

    'Gold, C., and T. Zesch, "CNN-Based Ruled Line Removal in Handwritten '
    'Documents," International Conference on Frontiers in Handwriting '
    'Recognition (ICFHR) 2022, LNCS 13639, pp. 530-544. '
    'DOI 10.1007/978-3-031-21648-0_36',

    'Ni, K., Y. Liang, and J. Xu, "Removal of Color-Document Image '
    'Show-Through Based on Self-Supervised Learning," Applied Sciences, '
    'Vol. 14, No. 11, 4568, 2024. DOI 10.3390/app14114568',

    'Likforman-Sulem, L., A. Zahour, and B. Taconet, "Text Line Segmentation '
    'of Historical Documents: a Survey," International Journal on Document '
    'Analysis and Recognition, Vol. 9, No. 2-4, pp. 123-138, 2007. '
    'arXiv:0704.1267',

    'Burrows, S., I. Gurevych, and B. Stein, "The Eras and Trends of Automatic '
    'Short Answer Grading," International Journal of Artificial Intelligence in '
    'Education, Vol. 25, No. 1, pp. 60-117, 2015. DOI 10.1007/s40593-014-0026-8',

    'Mohler, M., R. Bunescu, and R. Mihalcea, "Learning to Grade Short Answer '
    'Questions using Semantic Similarity Measures and Dependency Graph '
    'Alignments," Proceedings of ACL-HLT 2011, pp. 752-762. '
    'https://aclanthology.org/P11-1076/',

    'Dzikovska, M. O., R. D. Nielsen, C. Brew, C. Leacock, D. Giampiccolo, '
    'L. Bentivogli, P. Clark, I. Dagan, and H. T. Dang, "SemEval-2013 Task 7: '
    'The Joint Student Response Analysis and 8th Recognizing Textual Entailment '
    'Challenge," *SEM / SemEval 2013, pp. 263-274. '
    'https://aclanthology.org/S13-2045/',

    'Byun, J., S. Rajwal, and S. Choi, "LLM-as-a-Grader: Practical Insights '
    'from Large Language Model for Short-Answer and Report Evaluation," '
    'arXiv:2511.10819, 2025. https://arxiv.org/abs/2511.10819',

    'Qiu, H., K. White, A. Ding, R. Costa, A. Hachem, Y. Ding, and Z. Chen, '
    '"SteLLA: A Structured Grading System Using LLMs with RAG," IEEE BigData '
    '2024; arXiv:2501.09092. https://arxiv.org/abs/2501.09092',

    'Deng, Y., M. Farber, S. Lee, and J. Tang, "Rubric-Conditioned LLM '
    'Grading: Alignment, Uncertainty, and Robustness," arXiv:2601.08843, 2025. '
    'https://arxiv.org/abs/2601.08843',

    'Rao, A., and C. Callison-Burch, "Autorubric: A Unifying Framework for '
    'Rubric-Based LLM Evaluation on Non-Verifiable Tasks," COLM 2026; '
    'arXiv:2603.00077. https://arxiv.org/abs/2603.00077',

    'Guo, C., G. Pleiss, Y. Sun, and K. Q. Weinberger, "On Calibration of '
    'Modern Neural Networks," Proceedings of the 34th International Conference '
    'on Machine Learning (ICML) 2017. https://arxiv.org/abs/1706.04599',

    'Kadavath, S., T. Conerly, A. Askell, et al., "Language Models (Mostly) '
    'Know What They Know," arXiv:2207.05221, 2022. '
    'https://arxiv.org/abs/2207.05221',

    'Tian, K., E. Mitchell, A. Zhou, A. Sharma, R. Rafailov, H. Yao, C. Finn, '
    'and C. D. Manning, "Just Ask for Calibration: Strategies for Eliciting '
    'Calibrated Confidence Scores from Language Models," EMNLP 2023. '
    'https://arxiv.org/abs/2305.14975',

    'Wang, X., J. Wei, D. Schuurmans, Q. Le, E. Chi, S. Narang, A. Chowdhery, '
    'and D. Zhou, "Self-Consistency Improves Chain of Thought Reasoning in '
    'Language Models," ICLR 2023. https://arxiv.org/abs/2203.11171',

    'Manakul, P., A. Liusie, and M. J. F. Gales, "SelfCheckGPT: Zero-Resource '
    'Black-Box Hallucination Detection for Generative Large Language Models," '
    'EMNLP 2023. https://arxiv.org/abs/2303.08896',

    'Zheng, L., W.-L. Chiang, Y. Sheng, S. Zhuang, Z. Wu, Y. Zhuang, Z. Lin, '
    'Z. Li, D. Li, E. P. Xing, H. Zhang, J. E. Gonzalez, and I. Stoica, '
    '"Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena," NeurIPS 2023 '
    'Datasets and Benchmarks. https://arxiv.org/abs/2306.05685',

    'Kamath, A., R. Jia, and P. Liang, "Selective Question Answering under '
    'Domain Shift," Proceedings of ACL 2020, pp. 5684-5696. '
    'https://aclanthology.org/2020.acl-main.503/',

    'Mozannar, H., and D. Sontag, "Consistent Estimators for Learning to Defer '
    'to an Expert," Proceedings of the 37th International Conference on '
    'Machine Learning (ICML) 2020. https://arxiv.org/abs/2006.01862',

    'van Strien, D., K. Beelen, M. Coll Ardanuy, K. Hosseini, B. McGillivray, '
    'and G. Colavizza, "Assessing the Impact of OCR Quality on Downstream NLP '
    'Tasks," Proceedings of ICAART 2020, Vol. 1: ARTIDIGH, pp. 484-496. '
    'DOI 10.5220/0009169004840496',

    'Hemmer, A., M. Coustaty, N. Bartolo, and J.-M. Ogier, "Confidence-Aware '
    'Document OCR Error Detection," arXiv:2409.04117, 2024. '
    'https://arxiv.org/abs/2409.04117',

    'Liu, T., A. Chatain, L. Kobel-Keller, G. Kortemeyer, T. Willwacher, and '
    'M. Sachan, "AI-assisted Automated Short Answer Grading of Handwritten '
    'University Level Mathematics Exams," arXiv:2408.11728, 2024. '
    'https://arxiv.org/abs/2408.11728',

    'Kortemeyer, G., J. Caspar, and D. Horica, "Artificial-Intelligence '
    'Grading Assistance for Handwritten Components of a Calculus Exam," '
    'arXiv:2510.05162, 2025. https://arxiv.org/abs/2510.05162',

    'Henkel, O., H. Roberts, L. Jaffe, and A. Holt, "Seeing the Big Picture: '
    'Evaluating Multimodal LLMs\' Ability to Interpret and Grade Handwritten '
    'Student Work," arXiv:2510.05538, 2025. https://arxiv.org/abs/2510.05538',

    'Chaudhary, A., S. Singla, A. Kumar, M. Lavania, and S. Gupta, "Evaluation '
    'of Handwritten Answers Against a Corpus of Answer Key and Related '
    'Knowledge Base," Proceedings of the International Conference on '
    'Communication and Computational Technologies, Lecture Notes in Networks '
    'and Systems, Springer Nature Singapore, 2026. '
    'DOI 10.1007/978-981-95-3498-2_19',

    'Ramesh, D., and S. K. Sanampudi, "An automated essay scoring systems: a '
    'systematic literature review," Artificial Intelligence Review, Vol. 55, '
    'pp. 2495-2527, 2022. DOI 10.1007/s10462-021-10068-2',
]


def references(r) -> None:
    r.chapter = 0  # references are not a numbered chapter
    r.doc.add_page_break()
    r.front_heading("References", page_break=False)
    r.para(
        "References are numbered in the order of their first citation in the "
        "text.", italic=True, space_after=12,
    )
    for i, ref in enumerate(REFERENCES, start=1):
        p = r.doc.add_paragraph()
        p.paragraph_format.left_indent = __import__("docx").shared.Inches(0.4)
        p.paragraph_format.first_line_indent = __import__("docx").shared.Inches(-0.4)
        p.paragraph_format.space_after = __import__("docx").shared.Pt(6)
        p.paragraph_format.line_spacing = 1.15
        run = p.add_run(f"[{i}]  ")
        run.bold = True
        run.font.name = "Times New Roman"
        run.font.size = __import__("docx").shared.Pt(10.5)
        run2 = p.add_run(ref)
        run2.font.name = "Times New Roman"
        run2.font.size = __import__("docx").shared.Pt(10.5)


def appendices(r) -> None:
    from meta import META

    # --- Appendix I --------------------------------------------------------
    r.doc.add_page_break()
    r.front_heading("Appendix I  —  API Endpoint Reference", page_break=False)
    r.para(
        "The complete HTTP surface of the system: 47 endpoints under "
        "`/api/v1`, plus `/health`. Every endpoint that reads handwriting or "
        "awards a mark additionally accepts `?engine=gemini|local|auto`.",
        space_after=10,
    )
    r.table(
        "Part 1 — answers, transcription and documents.",
        ["Method", "Endpoint", "Purpose"],
        [
            ["POST", "`/answers`", "Register an answer image"],
            ["POST", "`/answers/transcribe`", "Upload and read in one call"],
            ["POST", "`/answers/{id}/ocr`", "Read a registered answer"],
            ["GET", "`/answers`", "Everything transcribed so far"],
            ["GET", "`/answers/{id}`", "One answer with its latest reading"],
            ["GET", "`/answers/{id}/image`", "The original handwriting"],
            ["GET", "`/answers/{id}/segmentation`", "The page with detected line boxes"],
            ["PATCH", "`/answers/{id}/ocr/verify`", "Save a human correction"],
            ["POST", "`/answers/{id}/ocr/accuracy`", "Character and word error rate"],
            ["POST", "`/documents/inspect`", "Page count and time estimate for a PDF"],
            ["POST", "`/documents/transcribe`", "Read a PDF booklet, optionally a page range"],
            ["GET", "`/documents/{ref}`", "Every page of one uploaded document"],
            ["GET", "`/ocr/provider`", "Which engine is loaded, and is it ready"],
            ["GET", "`/engines`", "Both engines and whether each can run now"],
            ["GET", "`/config/thresholds`", "The four trust bands"],
        ],
        widths=[0.65, 2.1, 2.5], font=8.8,
    )
    r.table(
        "Part 2 — questions and rubrics.",
        ["Method", "Endpoint", "Purpose"],
        [
            ["GET / POST", "`/exams`", "List papers; create an empty paper"],
            ["GET", "`/exams/{id}`", "One paper with its questions"],
            ["DELETE", "`/exams/{id}`", "Delete a paper not yet marked against"],
            ["POST", "`/exams/seed`", "Load the bundled paper (idempotent)"],
            ["GET", "`/exams/{id}/validate`", "Rubric validation, including the sum invariant"],
            ["GET", "`/exams/{id}/export`", "The paper as seed JSON"],
            ["POST", "`/exams/import`", "Create a paper from seed JSON"],
            ["POST", "`/exams/parse-document`", "**Read a Word/PDF marking scheme; returns a proposal**"],
            ["POST", "`/exams/{id}/questions`", "Add a question"],
            ["GET / PATCH / DELETE", "`/questions/{id}`", "Read, edit, remove a question"],
            ["GET / PUT", "`/questions/{id}/rubric`", "Read; write a new rubric version"],
            ["GET", "`/questions/{id}/rubric/versions`", "Rubric version history"],
            ["GET / PUT", "`/questions/{id}/answer-key`", "Read; write a new answer-key version"],
        ],
        widths=[1.2, 1.85, 2.2], font=8.8,
    )
    r.table(
        "Parts 3 and 4 — evaluation, review and validation.",
        ["Method", "Endpoint", "Purpose"],
        [
            ["POST", "`/evaluations`", "Mark one answer against one question"],
            ["GET", "`/evaluations`", "The marking queue, filterable by band"],
            ["GET", "`/evaluations/{id}`", "One evaluation with its criterion breakdown"],
            ["GET", "`/evaluations/provider`", "Which marker is configured"],
            ["GET", "`/answers/{id}/evaluations`", "Every evaluation of one answer"],
            ["GET", "`/documents/{ref}/segmentation`", "Where each question sits in a booklet"],
            ["POST", "`/documents/evaluate`", "Mark a whole booklet"],
            ["POST", "`/reviews`", "Record an examiner accept or modify"],
            ["GET", "`/evaluations/{id}/reviews`", "Review history for one evaluation"],
            ["GET", "`/analytics/summary`", "Machine-human agreement, by band"],
            ["GET", "`/config/confidence-weights`", "The four signal weights"],
            ["GET", "`/roadmap`", "What is built, and what is proven"],
        ],
        widths=[0.65, 2.1, 2.5], font=8.8,
    )

    # --- Appendix II -------------------------------------------------------
    r.doc.add_page_break()
    r.front_heading("Appendix II  —  A Worked Rubric", page_break=False)
    r.para(
        "Question 1 of the evaluation paper, as stored. This is the complete "
        "structure a marker receives: the question, its maximum marks, the "
        "answer key, and one entry per criterion carrying what the criterion is "
        "really testing rather than words to match literally.",
        space_after=10,
    )
    r.para("**Q1 (5 marks, theory, control structures).** State the difference "
           "between a while loop and a do-while loop. Give the syntax of each, "
           "and state one situation where do-while is the better choice.",
           space_after=10)
    r.table(
        "The four criteria of Q1 and their marks.",
        ["#", "Criterion", "Marks", "Essential concepts", "Partial?"],
        [
            ["1", "States that while checks the condition before executing the body",
             "1.5", "condition checked before body; entry controlled", "No"],
            ["2", "States that do-while checks the condition after executing the body",
             "1.5", "condition checked after body; exit controlled", "No"],
            ["3", "States that the do-while body executes at least once",
             "1.0", "executes at least once", "No"],
            ["4", "Gives a correct situation where do-while is preferable",
             "1.0", "must run at least once; menu-driven input", "Yes"],
            ["", "**Total**", "**5.0**", "matches the question's maximum", ""],
        ],
        widths=[0.3, 2.1, 0.5, 1.9, 0.55], font=8.6,
    )
    r.para(
        "Criteria 1 to 3 set `allows_partial` to false: a half-stated "
        "definition of loop control is not half correct. The acceptable "
        "alternatives recorded for criterion 1 include “pre-test loop”, "
        "“tests at the top” and “may run zero times”, so a "
        "student using any of those phrasings scores in full. The common "
        "mistake recorded is “says while runs at least once”.",
    )

    # --- Appendix III ------------------------------------------------------
    r.doc.add_page_break()
    r.front_heading("Appendix III  —  Reproducing the Measurements",
                    page_break=False)
    r.para(
        "Every figure and table in Chapter 4 can be regenerated from the "
        "repository. The commands below assume a Windows shell at the "
        "repository root with the virtual environment created.",
        space_after=10,
    )
    r.para("**Setup**", space_after=4)
    r.code(
        "python -m venv .venv\n"
        ".venv\\Scripts\\activate\n"
        "pip install -r requirements.txt\n"
        "cd frontend && npm install && cd .."
    )
    r.para("**Run the system**", space_after=4)
    r.code(
        "powershell -ExecutionPolicy Bypass -File scripts\\start.ps1\n"
        "#  API      http://localhost:8000/docs\n"
        "#  Interface http://localhost:5173"
    )
    r.para("**Reproduce the accuracy measurements of Section 4.3 and 4.7**",
           space_after=4)
    r.code(
        ".venv\\Scripts\\python scripts\\measure_engines.py ^\n"
        "    --engines local,gemini ^\n"
        "    --out docs\\report\\data\\engine_measurements.json"
    )
    r.para("**Run the test suite of Section 4.9**", space_after=4)
    r.code("cd backend && ..\\.venv\\Scripts\\python -m unittest discover -s tests -t .")
    r.para("**Regenerate this report**", space_after=4)
    r.code(
        ".venv\\Scripts\\python scripts\\report\\figures.py\n"
        ".venv\\Scripts\\python scripts\\report\\build_report.py"
    )
    r.para(
        f"The source repository is available at {META['repository']}. The "
        f"evaluation pages and the API key are excluded from version control: "
        f"the pages because the writers are identifiable from their "
        f"handwriting, and the key because it is a credential.",
        space_after=10,
    )
    r.table(
        "Configuration settings that affect the measurements.",
        ["Setting", "Default", "Effect"],
        [
            ["`EVALNOVA_OCR_PROVIDER`", "`trocr`", "Default recognition engine"],
            ["`EVALNOVA_EVALUATION_PROVIDER`", "`mock`", "Default marking engine"],
            ["`EVALNOVA_OCR_CONFIDENCE_SAMPLES`", "2", "Readings per page; 1 disables the confidence measurement"],
            ["`EVALNOVA_EVALUATION_SAMPLES`", "2", "Markings per answer; 1 disables the agreement signal"],
            ["`EVALNOVA_GEMINI_REQUESTS_PER_MINUTE`", "15", "The shared quota limiter; 0 disables it"],
            ["`EVALNOVA_OCR_MAX_CONCURRENCY`", "4", "Pages read in parallel"],
            ["`EVALNOVA_EVALUATION_MAX_CONCURRENCY`", "6", "Answers marked in parallel"],
        ],
        widths=[2.2, 0.75, 2.3], font=8.6,
    )
