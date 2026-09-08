"""
analysis.py
------------
Ce module prend le CSV brut produit par `generate_data.py` et calcule les
indicateurs (KPI) qu'une équipe CSIRT suivrait réellement : volume
d'incidents ouverts vs résolus, temps moyen de résolution par sévérité,
répartition par type, tendance hebdomadaire, et détection des incidents
qui dépassent leur SLA (Service Level Agreement).

Il produit aussi `data/incidents_clean.csv`, une version enrichie des
données (colonnes calculées en plus), pensée pour être branchée
directement dans un outil de BI comme Power BI : l'idée est de faire le
travail de préparation ("data cleaning/feature engineering") une fois en
Python, pour que le dashboard n'ait ensuite qu'à afficher, pas à
recalculer des colonnes complexes en DAX.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from src.generate_data import SEVERITES

# ---------------------------------------------------------------------------
# Configuration des SLA (Service Level Agreement)
# ---------------------------------------------------------------------------
# Un SLA de sécurité définit le délai maximum acceptable pour traiter un
# incident, selon sa gravité. Plus un incident est critique, plus le délai
# toléré est court : un incident critique (ex: ransomware actif) doit être
# traité en quelques heures, alors qu'un incident faible peut attendre
# quelques jours sans risque majeur pour l'organisation.
#
# Ces seuils sont exprimés en JOURS pour rester lisibles, mais dans un
# vrai contexte CSIRT, les SLA critiques sont souvent en heures.
SLA_JOURS_PAR_SEVERITE = {
    "critique": 1,
    "élevée": 3,
    "moyenne": 5,
    "faible": 10,
}

# Statuts considérés comme "encore actifs" (pas terminés) vs "clos".
STATUTS_OUVERTS = ["ouvert", "en cours"]
STATUTS_RESOLUS = ["résolu", "fermé"]


def charger_donnees(chemin: str) -> pd.DataFrame:
    """Charge le CSV brut et convertit les colonnes de dates en vrais
    objets datetime (par défaut, pandas les lirait comme du texte).

    `date_resolution` peut être vide (NaT) pour les incidents non
    résolus : pandas gère ça nativement avec `pd.to_datetime`, il suffit
    de ne pas paniquer sur les valeurs manquantes.
    """
    df = pd.read_csv(chemin, encoding="utf-8")
    df["date_ouverture"] = pd.to_datetime(df["date_ouverture"])
    df["date_resolution"] = pd.to_datetime(df["date_resolution"])
    return df


def nettoyer_donnees(df: pd.DataFrame, aujourdhui: pd.Timestamp | None = None) -> pd.DataFrame:
    """Enrichit le DataFrame brut avec des colonnes calculées utiles pour
    l'analyse et pour Power BI.

    Colonnes ajoutées :
    - `est_resolu` : booléen, True si statut = résolu ou fermé.
    - `semaine_ouverture` : le lundi de la semaine d'ouverture (permet de
      grouper facilement les incidents par semaine, en Python comme dans
      Power BI).
    - `sla_cible_jours` : le délai maximum toléré pour ce niveau de
      sévérité (voir SLA_JOURS_PAR_SEVERITE).
    - `jours_ouverture` : nombre de jours écoulés entre l'ouverture et soit
      la résolution (si résolu), soit aujourd'hui (si encore ouvert).
    - `sla_respecte` : pour un incident résolu, True/False selon qu'il a
      été traité dans les temps. Vide (NA) pour un incident encore ouvert
      -- on ne peut pas encore savoir s'il respectera le SLA.
    - `sla_actuellement_depasse` : pour un incident encore ouvert, True
      s'il a déjà dépassé son délai SLA à l'heure actuelle. Toujours
      False pour un incident résolu (la question ne se pose plus).

    Séparer "nettoyage/enrichissement" (ici) du "calcul des KPI agrégés"
    (fonctions plus bas) suit un principe simple : une fonction, une
    responsabilité. Ça permet aussi de réutiliser `nettoyer_donnees`
    ailleurs sans être obligé de calculer tous les KPI en même temps.
    """
    if aujourdhui is None:
        aujourdhui = pd.Timestamp(dt.datetime.now().date())

    df = df.copy()

    df["est_resolu"] = df["statut"].isin(STATUTS_RESOLUS)

    # `to_period("W")` regroupe par semaine (lundi à dimanche) ;
    # `.start_time` donne la date du lundi, plus lisible qu'un objet
    # Period pour un export CSV / Power BI.
    df["semaine_ouverture"] = df["date_ouverture"].dt.to_period("W").dt.start_time

    df["sla_cible_jours"] = df["severite"].map(SLA_JOURS_PAR_SEVERITE)

    # Pour un incident résolu : durée réelle de traitement (en jours).
    # Pour un incident encore ouvert : durée écoulée jusqu'à aujourd'hui.
    # np.where n'est pas nécessaire ici, pandas gère bien le mélange via
    # fillna + calcul conditionnel avec .where().
    duree_si_resolu = (df["date_resolution"] - df["date_ouverture"]).dt.total_seconds() / 86400
    duree_si_ouvert = (aujourdhui - df["date_ouverture"]).dt.total_seconds() / 86400
    df["jours_ouverture"] = duree_si_resolu.where(df["est_resolu"], duree_si_ouvert).round(2)

    # SLA respecté : uniquement calculable pour les incidents résolus.
    df["sla_respecte"] = pd.NA
    masque_resolu = df["est_resolu"]
    df.loc[masque_resolu, "sla_respecte"] = (
        df.loc[masque_resolu, "jours_ouverture"] <= df.loc[masque_resolu, "sla_cible_jours"]
    )

    # SLA dépassé MAINTENANT : uniquement pertinent pour les incidents
    # encore ouverts (un incident résolu n'est plus "en train" de
    # dépasser quoi que ce soit, même s'il a été traité en retard --
    # c'est capturé par `sla_respecte = False` à la place).
    df["sla_actuellement_depasse"] = (~df["est_resolu"]) & (df["jours_ouverture"] > df["sla_cible_jours"])

    return df


def calculer_kpi_ouverts_vs_resolus(df: pd.DataFrame) -> dict:
    """Compte simple : combien d'incidents sont encore actifs (ouvert /
    en cours) vs terminés (résolu / fermé), et le pourcentage résolu.

    C'est le KPI le plus basique d'un tableau de bord d'incident : il
    donne une photo instantanée de la charge de travail restante.
    """
    n_total = len(df)
    n_ouverts = int(df["statut"].isin(STATUTS_OUVERTS).sum())
    n_resolus = n_total - n_ouverts
    return {
        "total": n_total,
        "ouverts": n_ouverts,
        "resolus": n_resolus,
        "pct_resolus": round(100 * n_resolus / n_total, 1) if n_total else 0.0,
    }


def calculer_temps_moyen_resolution_par_severite(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule le temps de résolution moyen, médian et le nombre
    d'incidents résolus, pour chaque niveau de sévérité.

    On garde à la fois la MOYENNE et la MÉDIANE : la moyenne est
    facilement tirée vers le haut par quelques incidents anormalement
    longs (cf. la distribution log-normale utilisée pour les générer),
    alors que la médiane reflète mieux le cas "typique". Un bon rapport
    KPI montre les deux plutôt que de cacher l'écart.

    Seuls les incidents résolus sont inclus (un incident encore ouvert
    n'a pas de temps de résolution à calculer).
    """
    df_resolus = df[df["est_resolu"]]

    resultat = (
        df_resolus.groupby("severite")["temps_resolution_heures"]
        .agg(temps_moyen_heures="mean", temps_median_heures="median", nb_incidents="count")
        .round(1)
    )

    # On force l'ordre logique (faible -> critique) plutôt que l'ordre
    # alphabétique par défaut de groupby, pour que les graphiques et
    # rapports soient lisibles dans le bon sens de gravité croissante.
    resultat = resultat.reindex(SEVERITES)
    return resultat


def calculer_repartition_par_type(df: pd.DataFrame) -> pd.DataFrame:
    """Compte le nombre (et le %) d'incidents par type, du plus au moins
    fréquent. Utile pour prioriser les efforts de prévention : si le
    phishing représente 40 % des incidents, c'est probablement là qu'un
    programme de sensibilisation aura le plus d'impact.
    """
    comptes = df["type_incident"].value_counts()
    pourcentages = (100 * comptes / len(df)).round(1)
    return pd.DataFrame({"nb_incidents": comptes, "pct": pourcentages})


def calculer_tendance_hebdomadaire(df: pd.DataFrame) -> pd.Series:
    """Compte le nombre d'incidents OUVERTS chaque semaine (basé sur
    `date_ouverture`), trié chronologiquement.

    Une tendance dans le temps permet de répondre à des questions comme
    "est-ce que le volume d'incidents augmente ?" ou "y a-t-il eu un pic
    après tel événement ?" -- une simple photo instantanée (KPI du
    dessus) ne le montre pas.
    """
    return df.groupby("semaine_ouverture").size().sort_index().rename("nb_incidents")


def identifier_incidents_sla_depasse(df: pd.DataFrame) -> pd.DataFrame:
    """Retourne la liste des incidents encore ouverts dont le délai SLA
    est actuellement dépassé, triés du plus en retard au moins en retard.

    C'est la colonne `sla_actuellement_depasse` calculée dans
    `nettoyer_donnees` qui fait le travail ; cette fonction ne fait que
    filtrer et trier pour produire une liste actionnable (celle qu'un
    responsable CSIRT regarderait chaque matin).
    """
    colonnes_utiles = [
        "id", "type_incident", "severite", "statut",
        "date_ouverture", "jours_ouverture", "sla_cible_jours",
    ]
    df_depasse = df[df["sla_actuellement_depasse"]][colonnes_utiles]
    return df_depasse.sort_values("jours_ouverture", ascending=False).reset_index(drop=True)


def generer_rapport_kpi(df: pd.DataFrame) -> dict:
    """Rassemble tous les KPI en un seul dictionnaire et les affiche de
    façon lisible dans la console. C'est le point d'entrée pratique pour
    obtenir une vue d'ensemble en un seul appel de fonction.
    """
    kpi_ouverts_resolus = calculer_kpi_ouverts_vs_resolus(df)
    temps_par_severite = calculer_temps_moyen_resolution_par_severite(df)
    repartition_type = calculer_repartition_par_type(df)
    tendance_hebdo = calculer_tendance_hebdomadaire(df)
    incidents_sla_depasse = identifier_incidents_sla_depasse(df)

    print("=" * 60)
    print("RAPPORT KPI -- Suivi des incidents de sécurité")
    print("=" * 60)

    print(f"\nTotal incidents : {kpi_ouverts_resolus['total']}")
    print(f"  Ouverts / en cours : {kpi_ouverts_resolus['ouverts']}")
    print(f"  Résolus / fermés   : {kpi_ouverts_resolus['resolus']} ({kpi_ouverts_resolus['pct_resolus']} %)")

    print("\nTemps de résolution par sévérité :")
    print(temps_par_severite.to_string())

    print("\nRépartition par type d'incident :")
    print(repartition_type.to_string())

    print(f"\nTendance hebdomadaire ({len(tendance_hebdo)} semaines) -- dernières semaines :")
    print(tendance_hebdo.tail(5).to_string())

    print(f"\nIncidents avec SLA actuellement dépassé : {len(incidents_sla_depasse)}")
    if len(incidents_sla_depasse) > 0:
        print(incidents_sla_depasse.to_string(index=False))

    print("=" * 60)

    return {
        "kpi_ouverts_resolus": kpi_ouverts_resolus,
        "temps_par_severite": temps_par_severite,
        "repartition_type": repartition_type,
        "tendance_hebdo": tendance_hebdo,
        "incidents_sla_depasse": incidents_sla_depasse,
    }


def sauvegarder_csv(df: pd.DataFrame, chemin: str) -> None:
    """Sauvegarde le DataFrame nettoyé/enrichi en CSV, prêt à être
    importé dans Power BI ou tout autre outil de BI.
    """
    df.to_csv(chemin, index=False, encoding="utf-8")
    print(f"[analysis] Données nettoyées sauvegardées dans : {chemin}")


if __name__ == "__main__":
    # Exécution autonome du module : charge le brut, nettoie, calcule les
    # KPI et exporte le CSV propre. Pratique pour tester sans passer par
    # main.py pendant le développement.
    donnees_brutes = charger_donnees("data/incidents.csv")
    donnees_propres = nettoyer_donnees(donnees_brutes)
    generer_rapport_kpi(donnees_propres)
    sauvegarder_csv(donnees_propres, "data/incidents_clean.csv")
