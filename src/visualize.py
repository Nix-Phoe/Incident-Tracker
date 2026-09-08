"""
visualize.py
-------------
Ce module génère les graphiques matplotlib/seaborn qui accompagnent le
rapport KPI produit par `analysis.py`. Trois graphiques sont créés :

1. Tendance temporelle : nombre d'incidents ouverts par semaine.
2. Répartition croisée : incidents par type ET par sévérité (barres
   empilées), pour voir non seulement quels types d'incidents sont
   fréquents, mais aussi lesquels génèrent le plus d'incidents graves.
3. Temps de résolution moyen par sévérité.

Chaque graphique est sauvegardé en PNG dans `outputs/figures/`. Ce
module réutilise volontairement les fonctions de calcul déjà écrites
dans `analysis.py` plutôt que de refaire les calculs ici : un graphique
ne devrait jamais recalculer sa propre donnée différemment du rapport
KPI, sinon les deux risquent de se contredire.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from src.analysis import calculer_temps_moyen_resolution_par_severite, calculer_tendance_hebdomadaire
from src.generate_data import SEVERITES

# ---------------------------------------------------------------------------
# Palette de couleurs "feu de circulation"
# ---------------------------------------------------------------------------
# Associer une couleur fixe à chaque sévérité (vert -> rouge) est une
# convention très répandue dans les outils de sécurité (SIEM, dashboards
# SOC) : ça permet de reconnaître la gravité d'un coup d'œil, sans même
# lire les étiquettes. On réutilise cette palette sur tous les graphiques
# pour que la couleur "critique" (rouge) reste cohérente partout.
COULEURS_SEVERITE = {
    "faible": "#4CAF50",     # vert
    "moyenne": "#FFC107",    # jaune
    "élevée": "#FF9800",     # orange
    "critique": "#F44336",   # rouge
}


def configurer_style() -> None:
    """Configure une fois pour toutes l'apparence de tous les graphiques
    du module (thème, taille de police). Centraliser ce réglage évite de
    le répéter dans chaque fonction de graphique.
    """
    sns.set_theme(style="whitegrid")
    plt.rcParams["figure.dpi"] = 100
    plt.rcParams["font.size"] = 11


def graphique_tendance_temporelle(df: pd.DataFrame, chemin_sortie: str) -> None:
    """Trace le nombre d'incidents ouverts par semaine, sous forme de
    courbe. Une tendance temporelle répond à une question qu'un simple
    total ne peut pas répondre : "la situation s'améliore-t-elle ou
    empire-t-elle ?"
    """
    tendance = calculer_tendance_hebdomadaire(df)

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(tendance.index, tendance.values, marker="o", markersize=4, linewidth=1.5, color="#3F51B5")
    ax.fill_between(tendance.index, tendance.values, alpha=0.1, color="#3F51B5")

    ax.set_title("Tendance des incidents ouverts par semaine", fontsize=14, fontweight="bold")
    ax.set_xlabel("Semaine d'ouverture")
    ax.set_ylabel("Nombre d'incidents")
    fig.autofmt_xdate(rotation=45)

    fig.tight_layout()
    fig.savefig(chemin_sortie, bbox_inches="tight")
    plt.close(fig)
    print(f"[visualize] Graphique sauvegardé : {chemin_sortie}")


def graphique_repartition_type_severite(df: pd.DataFrame, chemin_sortie: str) -> None:
    """Trace un graphique à barres empilées horizontales : un type
    d'incident par ligne, une barre segmentée par sévérité.

    Ce croisement type x sévérité est plus riche qu'un simple comptage
    par type : deux types peuvent avoir le même volume total, mais l'un
    peut être surtout "faible" (peu inquiétant) et l'autre surtout
    "critique" (à traiter en priorité). C'est justement ce genre de
    nuance qu'un tableau de bord de sécurité doit mettre en évidence.
    """
    # Tableau croisé : lignes = type d'incident, colonnes = sévérité,
    # valeurs = nombre d'incidents.
    tableau_croise = pd.crosstab(df["type_incident"], df["severite"])
    # On force l'ordre des colonnes (faible -> critique) pour que
    # l'empilement suive toujours le même dégradé de couleur.
    tableau_croise = tableau_croise.reindex(columns=SEVERITES, fill_value=0)
    # On trie les lignes par volume total décroissant, pour que le type
    # d'incident le plus fréquent apparaisse en haut.
    tableau_croise = tableau_croise.loc[tableau_croise.sum(axis=1).sort_values(ascending=False).index]

    couleurs = [COULEURS_SEVERITE[s] for s in tableau_croise.columns]

    fig, ax = plt.subplots(figsize=(10, 6))
    tableau_croise.plot(kind="barh", stacked=True, color=couleurs, ax=ax, width=0.7)

    ax.set_title("Répartition des incidents par type et sévérité", fontsize=14, fontweight="bold")
    ax.set_xlabel("Nombre d'incidents")
    ax.set_ylabel("Type d'incident")
    ax.legend(title="Sévérité", bbox_to_anchor=(1.02, 1), loc="upper left")

    fig.tight_layout()
    fig.savefig(chemin_sortie, bbox_inches="tight")
    plt.close(fig)
    print(f"[visualize] Graphique sauvegardé : {chemin_sortie}")


def graphique_temps_resolution_par_severite(df: pd.DataFrame, chemin_sortie: str) -> None:
    """Trace un graphique à barres du temps de résolution MOYEN par
    sévérité, avec l'effectif affiché au-dessus de chaque barre.

    On utilise une échelle logarithmique sur l'axe Y : le temps moyen
    passe d'environ 5h (faible) à plus de 190h (critique), un facteur
    ~40. Sur une échelle linéaire classique, les barres "faible" et
    "moyenne" seraient quasiment invisibles à côté de "critique". Une
    échelle log garde chaque catégorie lisible -- un compromis courant
    en visualisation de données quand les valeurs couvrent plusieurs
    ordres de grandeur.
    """
    stats = calculer_temps_moyen_resolution_par_severite(df)

    fig, ax = plt.subplots(figsize=(8, 5))
    couleurs = [COULEURS_SEVERITE[s] for s in stats.index]
    barres = ax.bar(stats.index, stats["temps_moyen_heures"], color=couleurs)

    ax.set_yscale("log")
    ax.set_title("Temps de résolution moyen par sévérité", fontsize=14, fontweight="bold")
    ax.set_xlabel("Sévérité")
    ax.set_ylabel("Temps de résolution moyen (heures, échelle log)")

    # Annoter chaque barre avec sa valeur exacte : sur une échelle log,
    # la hauteur seule est difficile à lire précisément à l'œil.
    for barre, valeur, effectif in zip(barres, stats["temps_moyen_heures"], stats["nb_incidents"]):
        ax.annotate(
            f"{valeur:.0f} h\n(n={effectif})",
            xy=(barre.get_x() + barre.get_width() / 2, valeur),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            fontsize=9,
        )

    fig.tight_layout()
    fig.savefig(chemin_sortie, bbox_inches="tight")
    plt.close(fig)
    print(f"[visualize] Graphique sauvegardé : {chemin_sortie}")


def generer_toutes_les_visualisations(df: pd.DataFrame, dossier_sortie: str = "outputs/figures") -> list[str]:
    """Génère les trois graphiques du module et retourne la liste des
    chemins de fichiers créés. Point d'entrée pratique pour main.py.
    """
    configurer_style()
    Path(dossier_sortie).mkdir(parents=True, exist_ok=True)

    chemins = {
        "tendance": f"{dossier_sortie}/tendance_temporelle.png",
        "repartition": f"{dossier_sortie}/repartition_type_severite.png",
        "resolution": f"{dossier_sortie}/temps_resolution_par_severite.png",
    }

    graphique_tendance_temporelle(df, chemins["tendance"])
    graphique_repartition_type_severite(df, chemins["repartition"])
    graphique_temps_resolution_par_severite(df, chemins["resolution"])

    return list(chemins.values())


if __name__ == "__main__":
    # Exécution autonome : recharge et nettoie les données comme le
    # ferait analysis.py, puis génère les graphiques. Permet de tester
    # ce module seul pendant le développement.
    from src.analysis import charger_donnees, nettoyer_donnees

    donnees_brutes = charger_donnees("data/incidents.csv")
    donnees_propres = nettoyer_donnees(donnees_brutes)
    generer_toutes_les_visualisations(donnees_propres)
