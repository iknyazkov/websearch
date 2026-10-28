"""TestDecodeOutput — port of internal/services/websearch/cloud/service_test.go.

Go's TestDecodeOutput unmarshals the canned linkup provider payload (const
testData) into the package's Output and asserts the decoded shape, then
pins the FIRST branch of snippetFromContent's precedence chain — the
payload's content is object form, so the helper "falls through to snippet
(already set)" (service_test.go:178).

Inventory rows 76-78 decide this file (rows win over general rules):
TEST_DATA holds the SAME bytes as the Go backtick raw string — the payload
embeds literal backslash-n and backslash-escaped quotes that the JSON
parser must see, so a non-raw Python string would pre-unwrap them and
change the fixture. The decode assertions run over json.loads(TEST_DATA):
unknown fields (provider, query, answer, usage, metrics, errors,
display_url, position, score, published_at, favicon_url, metadata,
citation, provider_raw, ...) simply remain present in the dict, mirroring
encoding/json's ignore-unknown-fields behavior; the port's decode path
must not reject them either. Go's typed decode errors on a malformed
results array where json.loads would not — no such case exists in this
fixture (row 77: no TODO needed).
"""

import json

from websearch.services.websearch.cloud.service import snippet_from_content

TEST_DATA = r"""
{
  "provider": "linkup",
  "query": "What is the latest news about AI?",
  "results": [
    {
      "title": "AI News - AiNewsBase | Latest Artificial Intelligence News",
      "url": "https://ainewsbase.com/ai-news/",
      "display_url": "ainewsbase.com/ai-news/",
      "snippet": "## AI News  \nWelcome to our AI news page, your one-stop source for all the latest developments in the world of artificial intelligence. From breakthroughs in machine learning and natural language processing, to the ethical considerations surrounding AI, we strive to bring you comprehensive coverage of this rapidly evolving field.\n## AI News & Information  \nOur team of expert writers and industry insiders keep a close eye on the latest trends and innovations, bringing you the most up-to-date and relevant news. So whether you’re a seasoned AI professional or just starting to explore the possibilities of this technology, we’ve got you covered.  \nArtificial intelligence (AI) is revolutionizing the way we live and work, with new developments and breakthroughs being announced on a regular basis. From self-driving cars and personalized healthcare, to improved cybersecurity and more efficient supply chain management, the potential applications of AI are vast and varied.  \nOne of the most exciting areas of AI research is machine learning, which enables computers to learn and improve their performance without being explicitly programmed. This has led to significant advances in image and speech recognition, natural language processing, and a range of other fields.\n## Artificial Intelligence News  \nIn the field of healthcare, AI is being used to analyze medical records and assist with diagnosis, as well as to identify potential outbreaks of infectious diseases. In the financial industry, AI is being used to identify fraudulent transactions and improve risk assessment. And in the transportation sector, self-driving cars and drones are being developed, which could greatly improve safety and efficiency.  \nWhile the potential benefits of AI are numerous, there are also valid concerns about the ethical implications of this technology. Issues such as bias in algorithms, the potential loss of jobs, and the potential for misuse must be carefully considered as we continue to explore the possibilities of AI.  \nStay up-to-date on all the latest AI news and developments by following our artificial intelligence news page. We bring you in-depth analysis and expert insights from leading industry figures, keeping you informed on the most important advancements in this exciting field.",
      "position": 1,
      "score": null,
      "published_at": null,
      "favicon_url": null,
      "content": {
        "format": "text",
        "text": "## AI News  \nWelcome to our AI news page, your one-stop source for all the latest developments in the world of artificial intelligence. From breakthroughs in machine learning and natural language processing, to the ethical considerations surrounding AI, we strive to bring you comprehensive coverage of this rapidly evolving field.\n## AI News & Information  \nOur team of expert writers and industry insiders keep a close eye on the latest trends and innovations, bringing you the most up-to-date and relevant news. So whether you’re a seasoned AI professional or just starting to explore the possibilities of this technology, we’ve got you covered.  \nArtificial intelligence (AI) is revolutionizing the way we live and work, with new developments and breakthroughs being announced on a regular basis. From self-driving cars and personalized healthcare, to improved cybersecurity and more efficient supply chain management, the potential applications of AI are vast and varied.  \nOne of the most exciting areas of AI research is machine learning, which enables computers to learn and improve their performance without being explicitly programmed. This has led to significant advances in image and speech recognition, natural language processing, and a range of other fields.\n## Artificial Intelligence News  \nIn the field of healthcare, AI is being used to analyze medical records and assist with diagnosis, as well as to identify potential outbreaks of infectious diseases. In the financial industry, AI is being used to identify fraudulent transactions and improve risk assessment. And in the transportation sector, self-driving cars and drones are being developed, which could greatly improve safety and efficiency.  \nWhile the potential benefits of AI are numerous, there are also valid concerns about the ethical implications of this technology. Issues such as bias in algorithms, the potential loss of jobs, and the potential for misuse must be carefully considered as we continue to explore the possibilities of AI.  \nStay up-to-date on all the latest AI news and developments by following our artificial intelligence news page. We bring you in-depth analysis and expert insights from leading industry figures, keeping you informed on the most important advancements in this exciting field.",
        "length": 2296
      },
      "metadata": {
        "author": null,
        "language": null,
        "source_type": "text",
        "image_url": null
      },
      "citation": {
        "provider": "linkup",
        "retrieved_at": "2026-08-12T17:11:36.942Z",
        "rank": 1
      },
      "provider_raw": null
    },
    {
      "title": "Latest AI News | Appscribed",
      "url": "https://appscribed.com/ai-news/page/3/",
      "display_url": "appscribed.com/ai-news/page/3/",
      "snippet": "# AI News  \nTrending News and Analysis from the world of Artificial Intelligence\n## Latest AI News  \n- [OpenAI Day 4: Canvas Extends To All ChatGPT Users: Features, Issues, and Sora Updates](https://appscribed.com/openai-day-4-canvas-features-sora-updates/)Day 4 OpenAI expands Canvas to all ChatGPT users, adding Python code execution and custom GPT integration. Updates on Sora access included.December 11, 2024\n- [Day 3 – OpenAI Sora Is Here: Features, Usage, Access, and Login Issues](https://appscribed.com/openai-sora-access-usage-login-issues/)OpenAI Sora launches, revolutionizing text-to-video creation. High demand delays access, but excitement soars for this much-awaited tool.December 10, 2024\n- [OpenAI o1 Model: AI That Manipulated and “Schemed” To Avoid Being Shut Down](https://appscribed.com/openai-o1-manipulated-schemed/)Recent research has uncovered a surprising and unsettling capability in advanced AI systems: the ability to \"scheme.\" Scheming refers to an AI covertly working to achieve its goals, even if it means lying, manipulating outputs, or bypassing oversight mechanisms. A team of researchers from Apollo Research put this idea to the test, evaluating several cutting-edge…December 9, 2024\n- [OpenAI Day 2 of “12 Days of OpenAI”: Key Highlights and Analysis](https://appscribed.com/openai-day-2-reinforcement-fine-tuning-unveiled/)On Day 2 of OpenAI's \"12 Days of OpenAI,\" the focus shifts to Reinforcement Fine-Tuning. What makes this a game-changer for developers and researchers?December 7, 2024\n- [OpenAI Introduces ChatGPT Pro and OpenAI o1 Pro Mode on Day 1 of “12 Days of OpenAI”](https://appscribed.com/openai-live-stream-day-1-chatgpt-pro-openai-o1-pro/)OpenAI kicks off \"12 Days of AI\" with ChatGPT Pro and o1 model, offering advanced problem-solving, reasoning capabilities, and multimodal AI features.December 6, 2024\n- [OpenAI Announces “12 Days of AI”: This “Shipmas” Promises Innovations](https://appscribed.com/12-days-of-ai-shipmas-openai/)OpenAI's '12 Days of AI' livestreams daily promises groundbreaking AI updates, including Sora text-to-video and smarter reasoning models. Explore More!December 5, 2024\n- [Amazon Nova: New AI Models Launched by Amazon at AWS re:Invent 2024](https://appscribed.com/amazon-nova-ai-model/)Curious about Amazon Nova? Explore Amazon's new AI tools for creating text, images, and videos, all powered by Amazon BedrockDecember 4, 2024\n- [OpenAI’s New ChatGPT Search Feature: How and Why Use It](https://appscribed.com/openai-chatgpt-search-feature-button/)Curious about ChatGPT Search? Discover how OpenAI’s latest feature gives you instant answers from the web right inside your chat.November 1, 2024\n- [What Happened to Homeworkify? Events That Led to Homeworkify’s Shutdown](https://appscribed.com/homeworkify-shutdown/)Curious about What Happened to Homeworkify? Homeworkify is down and has stopped working. We discovered the real reasons behind it and whats next!September 23, 2024",
      "position": 2,
      "score": null,
      "published_at": null,
      "favicon_url": null,
      "content": {
        "format": "text",
        "text": "# AI News  \nTrending News and Analysis from the world of Artificial Intelligence\n## Latest AI News  \n- [OpenAI Day 4: Canvas Extends To All ChatGPT Users: Features, Issues, and Sora Updates](https://appscribed.com/openai-day-4-canvas-features-sora-updates/)Day 4 OpenAI expands Canvas to all ChatGPT users, adding Python code execution and custom GPT integration. Updates on Sora access included.December 11, 2024\n- [Day 3 – OpenAI Sora Is Here: Features, Usage, Access, and Login Issues](https://appscribed.com/openai-sora-access-usage-login-issues/)OpenAI Sora launches, revolutionizing text-to-video creation. High demand delays access, but excitement soars for this much-awaited tool.December 10, 2024\n- [OpenAI o1 Model: AI That Manipulated and “Schemed” To Avoid Being Shut Down](https://appscribed.com/openai-o1-manipulated-schemed/)Recent research has uncovered a surprising and unsettling capability in advanced AI systems: the ability to \"scheme.\" Scheming refers to an AI covertly working to achieve its goals, even if it means lying, manipulating outputs, or bypassing oversight mechanisms. A team of researchers from Apollo Research put this idea to the test, evaluating several cutting-edge…December 9, 2024\n- [OpenAI Day 2 of “12 Days of OpenAI”: Key Highlights and Analysis](https://appscribed.com/openai-day-2-reinforcement-fine-tuning-unveiled/)On Day 2 of OpenAI's \"12 Days of OpenAI,\" the focus shifts to Reinforcement Fine-Tuning. What makes this a game-changer for developers and researchers?December 7, 2024\n- [OpenAI Introduces ChatGPT Pro and OpenAI o1 Pro Mode on Day 1 of “12 Days of OpenAI”](https://appscribed.com/openai-live-stream-day-1-chatgpt-pro-openai-o1-pro/)OpenAI kicks off \"12 Days of AI\" with ChatGPT Pro and o1 model, offering advanced problem-solving, reasoning capabilities, and multimodal AI features.December 6, 2024\n- [OpenAI Announces “12 Days of AI”: This “Shipmas” Promises Innovations](https://appscribed.com/12-days-of-ai-shipmas-openai/)OpenAI's '12 Days of AI' livestreams daily promises groundbreaking AI updates, including Sora text-to-video and smarter reasoning models. Explore More!December 5, 2024\n- [Amazon Nova: New AI Models Launched by Amazon at AWS re:Invent 2024](https://appscribed.com/amazon-nova-ai-model/)Curious about Amazon Nova? Explore Amazon's new AI tools for creating text, images, and videos, all powered by Amazon BedrockDecember 4, 2024\n- [OpenAI’s New ChatGPT Search Feature: How and Why Use It](https://appscribed.com/openai-chatgpt-search-feature-button/)Curious about ChatGPT Search? Discover how OpenAI’s latest feature gives you instant answers from the web right inside your chat.November 1, 2024\n- [What Happened to Homeworkify? Events That Led to Homeworkify’s Shutdown](https://appscribed.com/homeworkify-shutdown/)Curious about What Happened to Homeworkify? Homeworkify is down and has stopped working. We discovered the real reasons behind it and whats next!September 23, 2024",
        "length": 2967
      },
      "metadata": {
        "author": null,
        "language": null,
        "source_type": "text",
        "image_url": null
      },
      "citation": {
        "provider": "linkup",
        "retrieved_at": "2026-08-12T17:11:36.942Z",
        "rank": 2
      },
      "provider_raw": null
    },
    {
      "title": "Latest News About AI: AI Delas Alas and Emerging Trends",
      "url": "https://aiagentmemory.org/articles/latest-news-about-ai-ai-delas-alas/",
      "display_url": "aiagentmemory.org/articles/latest-news-about-ai-ai-delas-alas/",
      "snippet": "What are the most recent breakthroughs and emerging trends in artificial intelligence? **Latest news about AI AI Delas Alas** encompasses new capabilities, research findings, and practical applications that are shaping AI’s future, particularly in memory systems and agent architectures. This information is crucial for understanding AI’s rapid evolution.\n## What is Latest News About AI AI Delas Alas?  \n**Latest news about AI AI Delas Alas** signifies the most recent unveilings and significant advancements in artificial intelligence research and application. This includes breakthroughs in how AI agents store and recall information, their underlying structural designs, and how they interact with complex environments and data, signaling new capabilities and emerging trends.  \nThe field of AI is accelerating rapidly. New research papers and product releases constantly push the boundaries of what’s possible. Understanding these developments is crucial for anyone involved in AI development or its application. Staying informed on the **latest news about AI AI Delas Alas** keeps you ahead of the curve.\n### Emerging Trends and Future Outlook  \nThe **latest news about AI AI Delas Alas** points towards a future where AI agents are more autonomous, adaptable, and capable. We can expect to see continued innovation in areas like **temporal reasoning in AI memory** and **AI agent episodic memory**.  \nThe development of **AI agents that remember conversations** will lead to more intuitive and helpful personal assistants. The ability for **AI agent persistent memory** to be integrated across different applications will create a more seamless and intelligent digital experience. The race is on to develop the most effective [best AI memory systems](https://aiagentmemory.org/articles/best-ai-memory-systems/).",
      "position": 3,
      "score": null,
      "published_at": null,
      "favicon_url": null,
      "content": {
        "format": "text",
        "text": "What are the most recent breakthroughs and emerging trends in artificial intelligence? **Latest news about AI AI Delas Alas** encompasses new capabilities, research findings, and practical applications that are shaping AI’s future, particularly in memory systems and agent architectures. This information is crucial for understanding AI’s rapid evolution.\n## What is Latest News About AI AI Delas Alas?  \n**Latest news about AI AI Delas Alas** signifies the most recent unveilings and significant advancements in artificial intelligence research and application. This includes breakthroughs in how AI agents store and recall information, their underlying structural designs, and how they interact with complex environments and data, signaling new capabilities and emerging trends.  \nThe field of AI is accelerating rapidly. New research papers and product releases constantly push the boundaries of what’s possible. Understanding these developments is crucial for anyone involved in AI development or its application. Staying informed on the **latest news about AI AI Delas Alas** keeps you ahead of the curve.\n### Emerging Trends and Future Outlook  \nThe **latest news about AI AI Delas Alas** points towards a future where AI agents are more autonomous, adaptable, and capable. We can expect to see continued innovation in areas like **temporal reasoning in AI memory** and **AI agent episodic memory**.  \nThe development of **AI agents that remember conversations** will lead to more intuitive and helpful personal assistants. The ability for **AI agent persistent memory** to be integrated across different applications will create a more seamless and intelligent digital experience. The race is on to develop the most effective [best AI memory systems](https://aiagentmemory.org/articles/best-ai-memory-systems/).",
        "length": 1818
      },
      "metadata": {
        "author": null,
        "language": null,
        "source_type": "text",
        "image_url": null
      },
      "citation": {
        "provider": "linkup",
        "retrieved_at": "2026-08-12T17:11:36.942Z",
        "rank": 3
      },
      "provider_raw": null
    },
    {
      "title": "AI Market News: Apple&#x27;s Talks With Google, xAI&#x27;s Open-Source Move and More | VKTR",
      "url": "https://www.vktr.com/ai-market/ai-market-news-apples-talks-with-google-xais-open-source-move-and-more/",
      "display_url": "vktr.com/ai-market/ai-market-news-apples-talks-with-google-xais-open-source-move-and-more/",
      "snippet": "Here's the latest news on artificial intelligence — just for you:\n## Apple Talking With Google About AI Models  \nCupertino, California-based Apple is [negotiating](https://www.bloomberg.com/news/articles/2024-03-18/apple-in-talks-to-license-google-gemini-for-iphone-ios-18-generative-ai-tools) a possible AI-related deal with Mountain View, California-based Google, according to Bloomberg. The deal would reportedly see Google’s Gemini LLM models power some new iPhone AI features. Apple also reportedly talked about a deal with OpenAI recently.\n## Adobe Integrating Firefly Into Substance 3D  \nThe San Jose, California-based digital experience company Adobe demonstrated some of its Firefly generative AI image features within its Substance 3D design workflows. Adobe believes the [integration](https://news.adobe.com/news/news-details/2024/Adobe-Brings-Firefly-Generative-AI-Into-Substance-3D-Workflows/default.aspx) will help industrial designers, game developers and VFX professionals accelerate their iterative and creative processes, including 3D texturing and background image generation.  \n**See more: [10 Top AI Companies Defining the Market](https://www.vktr.com/ai-market/10-top-ai-companies-defining-the-market/)**",
      "position": 4,
      "score": null,
      "published_at": null,
      "favicon_url": null,
      "content": {
        "format": "text",
        "text": "Here's the latest news on artificial intelligence — just for you:\n## Apple Talking With Google About AI Models  \nCupertino, California-based Apple is [negotiating](https://www.bloomberg.com/news/articles/2024-03-18/apple-in-talks-to-license-google-gemini-for-iphone-ios-18-generative-ai-tools) a possible AI-related deal with Mountain View, California-based Google, according to Bloomberg. The deal would reportedly see Google’s Gemini LLM models power some new iPhone AI features. Apple also reportedly talked about a deal with OpenAI recently.\n## Adobe Integrating Firefly Into Substance 3D  \nThe San Jose, California-based digital experience company Adobe demonstrated some of its Firefly generative AI image features within its Substance 3D design workflows. Adobe believes the [integration](https://news.adobe.com/news/news-details/2024/Adobe-Brings-Firefly-Generative-AI-Into-Substance-3D-Workflows/default.aspx) will help industrial designers, game developers and VFX professionals accelerate their iterative and creative processes, including 3D texturing and background image generation.  \n**See more: [10 Top AI Companies Defining the Market](https://www.vktr.com/ai-market/10-top-ai-companies-defining-the-market/)**",
        "length": 1226
      },
      "metadata": {
        "author": null,
        "language": null,
        "source_type": "text",
        "image_url": null
      },
      "citation": {
        "provider": "linkup",
        "retrieved_at": "2026-08-12T17:11:36.942Z",
        "rank": 4
      },
      "provider_raw": null
    },
    {
      "title": "AI Market News: Adobe&#x27;s AI Video, Samsung&#x27;s Billions and More | VKTR",
      "url": "https://www.vktr.com/ai-market/ai-market-news-adobes-ai-video-samsungs-billions-and-more/",
      "display_url": "vktr.com/ai-market/ai-market-news-adobes-ai-video-samsungs-billions-and-more/",
      "snippet": "Here's the latest news on artificial intelligence — just for you:\n## Adobe Extending Acrobat AI Assistant  \nAdobe is making the “full range” of its Acrobat AI Assistant capabilities for PDFs available to “billions” of users across Acrobat Reader, Acrobat desktop and Acrobat web through an add-on subscription, which starts at $4.99 a month. Acrobat AI Assistant is also now available on mobile in beta. The [assistant](https://news.adobe.com/news/news-details/2024/Adobe-transforms-digital-document-experiences-this-tax-season-with-general-availability-of-Acrobat-AI-Assistant/default.aspx) launched in beta in February.\n## Amazon Appoints Andrew Ng to Board  \nSeattle-based Amazon named Andrew Ng to its board of directors, effective April 9. Ng’s background in AI is extensive: he’s the managing general partner of the AI Fund, a venture studio; founder of DeepLearning.AI, a learning platform; founder of Landing AI, a provider of computer vision software; co-founder and chair of Coursera, a learning platform; and adjunct professor at Stanford University. Previously, [Ng](https://www.aboutamazon.com/news/company-news/dr-andrew-ng-joins-amazon-board-of-directors) was chief scientist and VP at Baidu and founding lead of the Google Brain Project.",
      "position": 5,
      "score": null,
      "published_at": null,
      "favicon_url": null,
      "content": {
        "format": "text",
        "text": "Here's the latest news on artificial intelligence — just for you:\n## Adobe Extending Acrobat AI Assistant  \nAdobe is making the “full range” of its Acrobat AI Assistant capabilities for PDFs available to “billions” of users across Acrobat Reader, Acrobat desktop and Acrobat web through an add-on subscription, which starts at $4.99 a month. Acrobat AI Assistant is also now available on mobile in beta. The [assistant](https://news.adobe.com/news/news-details/2024/Adobe-transforms-digital-document-experiences-this-tax-season-with-general-availability-of-Acrobat-AI-Assistant/default.aspx) launched in beta in February.\n## Amazon Appoints Andrew Ng to Board  \nSeattle-based Amazon named Andrew Ng to its board of directors, effective April 9. Ng’s background in AI is extensive: he’s the managing general partner of the AI Fund, a venture studio; founder of DeepLearning.AI, a learning platform; founder of Landing AI, a provider of computer vision software; co-founder and chair of Coursera, a learning platform; and adjunct professor at Stanford University. Previously, [Ng](https://www.aboutamazon.com/news/company-news/dr-andrew-ng-joins-amazon-board-of-directors) was chief scientist and VP at Baidu and founding lead of the Google Brain Project.",
        "length": 1253
      },
      "metadata": {
        "author": null,
        "language": null,
        "source_type": "text",
        "image_url": null
      },
      "citation": {
        "provider": "linkup",
        "retrieved_at": "2026-08-12T17:11:36.942Z",
        "rank": 5
      },
      "provider_raw": null
    }
  ],
  "answer": null,
  "usage": {
    "queries_used": 1,
    "search_cost_usd": 0.005
  },
  "metrics": {
    "response_time_ms": 1600,
    "upstream_latency_ms": 1600,
    "total_results_available": 5
  },
  "errors": []
}
"""


def test_decode_output() -> None:
    doc = json.loads(TEST_DATA)
    assert len(doc["results"]) == 5
    r = doc["results"][0]
    assert r["title"] and r["url"] and r["snippet"]
    assert r["content"]
    # The service's raw-span record (present, parsed_value, raw_span) stands
    # in for Go's decoded r.Content: the fixture's snippet is non-empty, so
    # snippet_from_content short-circuits at the FIRST branch and never
    # inspects content — json.dumps(r["content"]) is a sound raw-span
    # stand-in (inventory row 76; the remaining branches of the precedence
    # matrix are owned by judge s02).
    content: tuple[bool, object, str] = (True, r["content"], json.dumps(r["content"]))
    # content is object form → snippetFromContent falls through to snippet (already set)
    assert snippet_from_content(r["snippet"], content) == r["snippet"]


# PORT STATUS: confidence=high todos=0
