from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask import send_from_directory
import pandas as pd
import requests
from collections import Counter
import os
from flask_socketio import SocketIO, emit
from threading import Thread, Event
import time

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Clé secrète pour les messages flash

# Emplacement temporaire pour stocker les fichiers
UPLOAD_FOLDER = "uploaded_files"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Variable globale pour stocker les données du fichier
data_from_xlsx = None

# Nom du fichier spécifique
SPECIFIC_FILE = "date.xlsx"
# Initialiser SocketIO
socketio = SocketIO(app)

# Événement pour annuler le traitement
cancel_event = Event()

def background_task(socketio, data, total_rows):
    """
    Traitement des données en arrière-plan pour mettre à jour les publications.
    """
    cancel_event.clear()
    processed_rows = 0

    for _, row in data.iterrows():
        if cancel_event.is_set():
            break  # Arrêter le traitement si annulé

        # Simuler une requête API HAL avec NOM COMPLET et NOM COMPLET2
        full_name = row["NOM COMPLET"]
        full_name2 = row["NOM COMPLET2"]
        # Ajouter ici la logique de requête HAL, comme `search_hal`

        # Simuler un délai pour chaque itération
        time.sleep(0.5)

        processed_rows += 1
        progress = int((processed_rows / total_rows) * 100)
        socketio.emit("progress_update", {"progress": progress}, namespace="/update")

    socketio.emit("task_complete", {"status": "finished"}, namespace="/update")

@app.route("/start_processing", methods=["POST"])
def start_processing():
    """
    Démarrer le traitement des données.
    """
    global cancel_event
    cancel_event.clear()

    # Charger les données du fichier Excel
    try:
        data = pd.read_excel(SPECIFIC_FILE)
        if not {"NOM COMPLET", "NOM COMPLET2"}.issubset(data.columns):
            raise ValueError("Les colonnes nécessaires sont manquantes.")
    except Exception as e:
        return {"status": "error", "message": str(e)}, 400

    # Lancer une tâche de traitement en arrière-plan
    total_rows = len(data)
    thread = Thread(target=background_task, args=(socketio, data, total_rows))
    thread.start()

    return {"status": "started"}

@app.route("/cancel_processing", methods=["POST"])
def cancel_processing():
    """
    Annuler le traitement des données.
    """
    cancel_event.set()
    return {"status": "cancelled"}

# Vérifier si le fichier existe
def load_excel_file():
    if os.path.exists(SPECIFIC_FILE):
        try:
            # Charger le fichier Excel
            data = pd.read_excel(SPECIFIC_FILE)
            if "LABO" not in data.columns:
                print("La colonne 'LABO' est absente du fichier.")
                raise ValueError("La colonne 'LABO' est absente du fichier.")
            return data
        except Exception as e:
            print(f"Erreur lors du chargement du fichier : {str(e)}")
            flash(f"Erreur lors du chargement du fichier : {str(e)}")
            return None
    else:
        flash(f"Le fichier '{SPECIFIC_FILE}' est introuvable.")
        print(f"Le fichier '{SPECIFIC_FILE}' est introuvable.")
        return None

@app.route("/", methods=["GET", "POST"])
def index():
    """Page principale avec barre de recherche et chargement de fichier."""
    global data_from_xlsx
    results = None
    error = None

    if request.method == "POST":
        if "search_query" in request.form:
            # Recherche via API HAL
            nom_complet = request.form["search_query"].strip()
            if not nom_complet:
                error = "Veuillez entrer un nom complet."
            else:
                results, error = search_hal(nom_complet)
        elif "file" in request.files:
            # Chargement d'un fichier .xlsx
            file = request.files["file"]
            if file and file.filename.endswith(".xlsx"):
                file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
                file.save(file_path)

                try:
                    # Traiter le fichier et charger les données traitées dans la variable globale
                    processed_file_path = process_uploaded_file(file_path)
                    flash(f"Fichier chargé et traité avec succès. Nouveau fichier : {os.path.basename(processed_file_path)}.")
                    return redirect(url_for("index"))
                except Exception as e:
                    error = str(e)
            else:
                error = "Veuillez télécharger un fichier .xlsx valide."

    return render_template("index.html", results=results, error=error, data=data_from_xlsx)





@app.route("/download/<filename>")
def download_file(filename):
    """Permet de télécharger un fichier traité."""
    try:
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)
    except Exception as e:
        flash(f"Erreur lors du téléchargement du fichier : {str(e)}")
        return redirect(url_for("index"))

@app.route("/update_database", methods=["GET", "POST"])
def update_database():
    """Page pour mettre à jour la base de données avec les publications HAL."""
    if request.method == "POST":
        # Si la requête POST est reçue, traiter les données
        action = request.form.get("action")
        if action == "start":
            # Démarrer le traitement des données (AJAX peut être utilisé pour cette partie)
            return jsonify({"status": "processing"}), 202
        elif action == "cancel":
            # Arrêter le traitement
            return jsonify({"status": "cancelled"}), 200

    # Afficher la page avec le bouton
    return render_template("update_database.html")

@app.route("/search_from_file", methods=["GET", "POST"])
def search_from_file():
    data = load_excel_file()

    # Si le fichier n'est pas valide, rester sur la page et afficher une erreur
    if data is None:
        print("Le fichier requis 'date.xlsx' est introuvable ou invalide.")
        flash("Le fichier requis 'date.xlsx' est introuvable ou invalide.")
        return render_template("search_from_file.html", labo_list=[], results=None, error=None)

    # Extraire les laboratoires uniques
    labo_list = data["LABO"].dropna().unique()

    results = None
    error = None

    if request.method == "POST":
        selected_labo = request.form.get("selected_labo")
        if selected_labo:
            # Filtrer les données par laboratoire sélectionné
            filtered_data = data[data["LABO"] == selected_labo]

            if filtered_data.empty:
                error = f"Aucune donnée trouvée pour le laboratoire : {selected_labo}"
            else:
                results = filtered_data.to_dict(orient="records")
        else:
            error = "Veuillez sélectionner un laboratoire."

    return render_template("search_from_file.html", labo_list=labo_list, results=results, error=error)

def process_uploaded_file(file_path):
    """
    Traite le fichier Excel chargé : corrige les noms des colonnes et génère de nouvelles colonnes.
    """
    try:
        # Charger les données depuis le fichier Excel
        data = pd.read_excel(file_path)

        # Renommer les colonnes
        column_mapping = {"Nom": "Nom", "Prenom": "Prénom", "Laboratoire": "LABO"}
        data.rename(columns=column_mapping, inplace=True)

        # Vérifier que les colonnes nécessaires existent après renommage
        if not {"Nom", "Prénom", "LABO"}.issubset(data.columns):
            raise ValueError("Les colonnes 'Nom', 'Prénom' et 'LABO' sont requises dans le fichier.")

        # Générer la colonne 'NOM COMPLET'
        data["NOM COMPLET"] = data["Prénom"].str.title() + " " + data["Nom"].str.title()

        # Générer la colonne 'NOM COMPLET2' avec les initiales du prénom
        def generate_initials(prenom):
            return ".".join([p[0].upper() for p in prenom.split("-")]) + "."

        data["NOM COMPLET2"] = data["Prénom"].apply(generate_initials) + " " + data["Nom"].str.title()

        # Déterminer le nouveau nom de fichier
        base_name = os.path.basename(file_path)
        new_name = f"data_propre.xlsx"
        new_path = os.path.join(os.path.dirname(file_path), new_name)

        # Sauvegarder le fichier traité avec le nouveau nom
        data.to_excel(new_path, index=False)

        # Retourner le chemin du fichier traité
        return new_path
    except Exception as e:
        raise ValueError(f"Erreur lors du traitement du fichier : {str(e)}")




def search_hal(nom_complet):
    """Recherche des données via l'API HAL."""
    hal_api_url = "https://api.archives-ouvertes.fr/search/"
    all_docids = set()
    results = {"stats": {}, "details": []}

    prenom = nom_complet.split()[0]
    nom = nom_complet.split()[1]
    nom_complet2 = ''.join([c+'.' for c in prenom if c.isupper()]) + ' ' + nom

    # Rechercher avec les deux formats de noms
    for query_name in [nom_complet, nom_complet2]:
        params = {
            "q": f"authFullName_s:\"{query_name}\"",
            "wt": "json",
            "fl": "docid",
            "rows": 100,
        }
        try:
            response = requests.get(hal_api_url, params=params)
            response.raise_for_status()
            data = response.json()
            docs = data.get("response", {}).get("docs", [])
            docids = [doc.get("docid") for doc in docs if doc.get("docid")]
            all_docids.update(docids)
        except Exception as e:
            return None, f"Erreur lors de la recherche : {str(e)}"

    if not all_docids:
        return None, "Aucun résultat trouvé."

    # Récupérer les détails des publications
    titles, authors, domains, labos = [], [], [], []
    for docid in all_docids:
        params = {
            "q": f"docid:\"{docid}\"",
            "wt": "json",
            "fl": "title_s,authFullName_s,domain_s,structName_s",
        }
        try:
            response = requests.get(hal_api_url, params=params)
            response.raise_for_status()
            data = response.json()
            docs = data.get("response", {}).get("docs", [])
            for doc in docs:
                title = doc.get("title_s", ["Sans titre"])[0]
                author_list = ", ".join(doc.get("authFullName_s", []))
                domain = ", ".join(doc.get("domain_s", []))
                labo = ", ".join(doc.get("structName_s", []))

                titles.append(title)
                authors.append(author_list)
                domains.extend(doc.get("domain_s", []))
                labos.extend(doc.get("structName_s", []))

                results["details"].append({"title": title, "authors": author_list, "domain": domain, "labo": labo})
        except Exception as e:
            return None, f"Erreur lors de la récupération des détails : {str(e)}"

    # Générer les statistiques
    domain_stats = Counter(domains)
    labo_stats = Counter(labos)
    results["stats"]["num_publications"] = len(all_docids)
    results["stats"]["domains"] = domain_stats
    results["stats"]["main_labo"] = labo_stats.most_common(1)[0][0] if labo_stats else "N/A"

    return results, None

def search_publications_for_lab(names):
    """Recherche des publications pour une liste de chercheurs."""
    all_results = []
    for name in names:
        results, error = search_hal(name)
        if results:
            all_results.append(results)

    return all_results, None

if __name__ == "__main__":
    app.run(debug=True)
