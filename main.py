"""
main.py
-------
Point d'entrée du projet : exécute le pipeline complet, de la génération
des données synthétiques jusqu'aux graphiques.

Le pipeline suit 3 étapes, chacune déléguée à son module dédié :

    1. Génération des données brutes   -> src/generate_data.py
    2. Nettoyage + calcul des KPI       -> src/analysis.py
    3. Génération des graphiques        -> src/visualize.py

Chaque étape LIT et ÉCRIT sur disque (fichiers CSV) plutôt que de se
passer les DataFrames uniquement en mémoire. C'est volontaire : ça
reproduit la façon dont fonctionne un vrai pipeline de données par
lots (batch), où chaque étape peut être relancée indépendamment (ex:
régénérer seulement les graphiques sans refaire l'analyse), inspectée
séparément (ouvrir le CSV brut pour vérifier une anomalie), voire
exécutée par un outil différent (Power BI qui lit `incidents_clean.csv`
sans jamais toucher au code Python).
"""

from __future__ import annotations

import argparse

from src.analysis import charger_donnees, generer_rapport_kpi, nettoyer_donnees
from src.analysis import sauvegarder_csv as sauvegarder_csv_propre
from src.generate_data import generer_dataset
from src.generate_data import sauvegarder_csv as sauvegarder_csv_brut
from src.visualize import generer_toutes_les_visualisations

CHEMIN_CSV_BRUT = "data/incidents.csv"
CHEMIN_CSV_PROPRE = "data/incidents_clean.csv"
DOSSIER_GRAPHIQUES = "outputs/figures"


def executer_pipeline(n_incidents: int = 200, seed: int = 42) -> dict:
    """Exécute les 3 étapes du pipeline dans l'ordre et retourne le
    rapport KPI final (pratique pour des tests automatisés plus tard,
    ou pour une utilisation interactive en notebook/console Python).
    """
    print("\n### ÉTAPE 1/3 -- Génération des données synthétiques ###")
    df_brut = generer_dataset(n_incidents=n_incidents, seed=seed)
    sauvegarder_csv_brut(df_brut, CHEMIN_CSV_BRUT)

    print("\n### ÉTAPE 2/3 -- Nettoyage et calcul des KPI ###")
    # On relit le CSV depuis le disque plutôt que de réutiliser `df_brut`
    # directement : ça vérifie que le fichier écrit à l'étape 1 est bien
    # celui qui est lu ici, exactement comme le ferait quelqu'un qui
    # lance `python -m src.analysis` séparément un autre jour.
    df_brut_relu = charger_donnees(CHEMIN_CSV_BRUT)
    df_propre = nettoyer_donnees(df_brut_relu)
    rapport = generer_rapport_kpi(df_propre)
    sauvegarder_csv_propre(df_propre, CHEMIN_CSV_PROPRE)

    print("\n### ÉTAPE 3/3 -- Génération des graphiques ###")
    chemins_graphiques = generer_toutes_les_visualisations(df_propre, DOSSIER_GRAPHIQUES)

    print("\nPipeline terminé avec succès.")
    print(f"  Données brutes   : {CHEMIN_CSV_BRUT}")
    print(f"  Données propres  : {CHEMIN_CSV_PROPRE} (à importer dans Power BI)")
    print(f"  Graphiques       : {', '.join(chemins_graphiques)}")

    return rapport


def _analyser_arguments() -> argparse.Namespace:
    """Définit les options de la ligne de commande.

    Exposer `n_incidents` et `seed` en CLI (plutôt que de les coder en
    dur) permet de régénérer un jeu de données différent (plus gros,
    ou avec une autre graine aléatoire) sans toucher au code.
    """
    parser = argparse.ArgumentParser(description="Pipeline du projet incident-tracker")
    parser.add_argument(
        "--n-incidents", type=int, default=200,
        help="Nombre d'incidents synthétiques à générer (défaut : 200)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Graine aléatoire, pour des résultats reproductibles (défaut : 42)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _analyser_arguments()
    executer_pipeline(n_incidents=arguments.n_incidents, seed=arguments.seed)
