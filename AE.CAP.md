# AI Capstone project - AI Engineering

Welcome to the **Advanced LLM Application Development Capstone Project**! This project is designed to empower learners with practical skills for building, deploying, and optimizing applications powered by Large Language Models (LLMs). 

You will apply your knowledge of APIs, embeddings, retrieval-augmented generation (RAG), AI agents, and ethical AI development to create impactful solutions in real-world scenarios.  

This module is more open-ended, allowing you to choose on which **case** to focus for your graded project.  

**Additionally, it will be updated periodically with more examples and suggestions.** 

<!-- toc -->

## Table of Contents

- Objective
- Case 1: Retrieval-Augmented Generation (RAG)-Powered Knowledge Assistant
- Case 2: AI Agent for Task Automation
- Case 3: Smart Document Search System
- Case 4: Multi-Modal AI Application
- Case 5: AI for Code Generation and Debugging
- Case 6: Dig deeper into more advanced topics or tools.
- Case 7: LLM Performance Tuning
- Evaluation Criteria for all cases:

# Objective



* Immerse yourself in the community; discuss with STLs and peers
* Develop and deploy prototypes using LLM APIs, LangChain, and RAG.
* Gain hands-on experience with tools like Streamlit, ChromaDB, and vector databases.
* Master prompt engineering and function calling techniques for tailored LLM outputs.
* Prepare for roles in AI/ML or as technical startup founders.

**Before proceeding, keep in mind that it is highly recommended to engage with our community on Discord or participate in the available workshops and open sessions for this module.**

**Important**:
You should create a readme.md file in the project folder including a clear description of the project’s purpose and what it achieves — readme.md file should include a paragraph to concisely explain the goal of their project, the problem it solves, and how it works.

# Case 1: Retrieval-Augmented Generation (RAG)-Powered Knowledge Assistant

**Objective**: Build a knowledge assistant that retrieves relevant data from external sources to provide precise and contextualized answers.

**Key Tools**: LangChain, ChromaDB, OpenAI API, Streamlit.

**Steps**:



1. **Data Preparation**:
    - Choose a dataset (e.g., company FAQs, product manuals, or educational content).
    - Process and embed the data using tools like OpenAI embeddings or Hugging Face.
2. **Vector Database Integration**:
    - Set up a vector database (e.g., ChromaDB) to store and retrieve embeddings.
3. **LangChain RAG**:
    - Create a chain combining retrieval and generation to build the assistant.
4. **Interactive UI**:
    - Use Streamlit to develop an intuitive user interface.
5. **Testing and Optimization**:
    - Test the assistant’s responses for accuracy and efficiency.
6. **Ethical Assessment**:
    - Document ethical considerations, including data privacy and bias mitigation.

**Outcome**: A fully functional knowledge assistant with a demo showcasing retrieval and generation capabilities.


# Case 2: AI Agent for Task Automation

**Objective**: Develop an AI agent capable of automating complex workflows such as data analysis, report generation, or customer support.

**Key Tools**: LangChain, Python/JavaScript, OpenAI Function Calling, external APIs.

**Steps**:



1. **Agent Design**:
    - Define the agent’s purpose and capabilities (e.g., analyzing sales data, generating summaries).
2. **Tool Integration**:
    - Equip the agent with tools such as API calls, database queries, or web scraping.
3. **Agent Execution**:
    - Implement advanced features like long-term memory, code execution, or multi-step reasoning.
4. **Interactive Prototyping**:
    - Build a prototype using Streamlit or another interface for live interaction.
5. **Evaluation**:
    - Assess the agent’s accuracy and responsiveness through user testing.
6. **Documentation**:
    - Provide a comprehensive report detailing functionality and ethical considerations.

**Outcome**: A practical AI agent that automates tasks and demonstrates LLM-powered automation.


# Case 3: Smart Document Search System

**Objective**: Build a tool for efficiently searching large sets of documents, such as legal contracts, research papers, or technical manuals.

**Key Tools**: LangChain, Vector Databases (e.g., ChromaDB, Pinecone), PDF/HTML loaders.

**Steps**:



1. **Document Ingestion**:
    - Load and preprocess documents into a vector database.
2. **Search and Retrieval**:
    - Implement a semantic search system using embeddings and vector similarity queries.
3. **Contextual Responses**:
    - Use an LLM to generate context-aware responses or summaries based on retrieved documents.
4. **User Interface**:
    - Develop a user-friendly interface to upload documents and query the system.

**Outcome**: A powerful search system for professionals to find and summarize information from large document collections.


# Case 4: Multi-Modal AI Application

**Objective**: Develop an AI application combining text and image processing capabilities.

**Key Tools**: OpenAI’s DALL-E, CLIP, Whisper, LangChain.

**Steps**:



1. **Image and Text Analysis**:
    - Allow users to upload images and generate captions or extract metadata.
2. **Cross-Modal Search**:
    - Build a system to retrieve relevant images or text based on user queries.
3. **Generative Features**:
    - Enable users to generate images from descriptions or vice versa.
4. **Interactive Application**:
    - Develop a user interface integrating text and image functionalities.

**Outcome**: An innovative multi-modal AI application demonstrating the synergy between text and images.


# Case 5: AI for Code Generation and Debugging

**Objective**: Develop an AI-powered coding assistant for generating code snippets, debugging, and optimizing code.

**Key Tools**: OpenAI Codex, LangChain, Flask/FastAPI.

**Steps**:



1. **Code Suggestions**:
    - Use LLMs to generate code snippets based on user requirements.
2. **Error Debugging**:
    - Implement functionality to analyze error messages and suggest fixes.
3. **Code Optimization**:
    - Provide recommendations for improving performance or readability.
4. **Interactive Environment**:
    - Build a web-based IDE or integrate with existing tools like VS Code.

**Outcome**: A coding assistant that improves developer productivity and learning.


# Case 6: Dig deeper into more advanced topics or tools.

After completing the AI Engineering main module, you may have noticed topics that felt particularly challenging or areas you didn’t have enough time to fully explore. If you choose to continue with this case, you can focus on one complex topic or several of them. Use this opportunity to deepen your understanding, gather new information, and explore ways to apply these concepts to your work environment. You can also document how the selected topics might be relevant for your personal or professional growth.

**Steps:**



1. **Select a Topic** \
   Identify one or more topics you want to explore in greater depth, either from the previous module or beyond the program’s scope, as long as it relates to AI. Alternatively, you can choose from the tasks and examples provided below.
2. **Documentation** \
   Take notes or create a plan, especially if the topic involves building or improving something for your work. If time permits, you can even start creating or implementing your idea.
3. **Submit Your Outcome** \
   Share a brief document summarizing your notes, conclusions, a step-by-step plan for a future outcome, or even an applied final result. Remember, you can also use [NotebookLM](https://notebooklm.google/) for that.

**Note:** If your work-related project cannot be shared due to security reasons, simply provide a brief descriptive document explaining the outcome.


# Case 7: LLM Performance Tuning

**Objective**: Evaluate the effects of tuning LLM parameters (e.g., temperature, top-p, max tokens) on output quality.

**Steps**:



1. **Define Tasks**:
    - Choose tasks like text generation, summarization, or creative writing.
2. **Experimentation**:
    - Run the same prompts with varied parameters and analyze the outputs.
3. **Insights**:
    - Identify best practices for optimizing LLM outputs for specific use cases.
4. **Create a dataset with your findings**
    - Create a CSV or other dataset with your experiments, inputs, outputs and parameters.

**Outcome**: Create a small presentation and have a good knowledge of various parameters.


# Evaluation Criteria for all cases:



1. **Outcome Quality**:
    * Completeness and functionality of the final project (e.g., chatbot, RAG application, or agent).
    * User interface and interaction quality (if applicable).
    * Clear description of the project’s purpose and what it achieves — readme.md file should include a paragraph to concisely explain the goal of their project, the problem it solves, and how it works.
2. **Learning Application**:
    * Effective use of tools like LangChain, ChromaDB, or LLM APIs.
    * Implementation of best practices in prompt engineering and application design.
3. **Ethical Considerations**:
    * Demonstrated awareness of ethical and privacy issues in AI application development.
4. **Presentation**:
    * Clear explanation of the project’s purpose, implementation, and impact.
    * Use of SCR (Situation, Complication, Resolution) or SMART (Specific, Measurable, Achievable, Relevant, Time-bound) frameworks.
