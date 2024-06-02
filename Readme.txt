Setup and Installation
----------------------
To run this project in Google Colab, follow these steps to set up the environment:

1. Open a new Google Colab notebook.

2. Install the required libraries by running the following commands in code cells:

%%capture
!pip install datasets
%%capture
!pip install tokenizers
%%capture
!pip install torchmetrics
%%capture
!pip install nltk

After installing NLTK, download the necessary datasets:

import nltk
nltk.download('punkt')
nltk.download('wordnet')

Import NLTK and other required modules:
from nltk.tokenize import word_tokenize
from nltk.translate.bleu_score import corpus_bleu
from nltk.translate.meteor_score import meteor_score

%%capture
!pip install rouge jiwer
from rouge import Rouge
from jiwer import cer, wer

%%capture
!pip install sacrebleu

%%capture
!pip install matplotlib
import matplotlib.pyplot as plt


Local Environment Setup
-----------------------

1. Ensure you have Python 3.9 installed on your machine.

2. Create a virtual environment

python -m venv myenv
source myenv/bin/activate  # On Windows use `myenv\Scripts\activate`


3.Install dependencies

pip install -r requirements.txt


Running the Code
----------------

- For Google Colab: After setting up the environment, you can copy the content of the project's `.ipynb` notebooks designed for Colab into new Colab notebook cells and run them.

- For Local Environment: Run the project's script from your terminal.
    1: run train.py for baseline model
    2: run trainnonselfatt,py for model employing "Non-Self-Referential Attention"
    3: run train_algo1.py for model employing "Soft Future Masking" and Algorithm1 with beta = -1e5 and gamma=-1e6
    4: run train_algo2.py for model employing "Soft Future Masking" and Algorithm2 with beta = -1e5 and gamma=-1e6
    5: run trainalgo1A.py for model employing "Soft Future Masking" and Algorithm1 with beta = 0.01 and gamma=0.02
    6: run trainalgo2B.py for model employing "Soft Future Masking" and Algorithm2 with beta = 0.01 and gamma=0.02

