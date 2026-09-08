"""
generate_data.py
-----------------
Ce module génère un jeu de données SYNTHÉTIQUE de tickets d'incidents de
sécurité, comme en produirait un outil de ticketing (ex: ServiceNow,
Jira Service Management) utilisé par une équipe CSIRT (Computer Security
Incident Response Team).

Aucune donnée réelle n'est utilisée : tout est généré aléatoirement,
mais avec des distributions statistiques réalistes (ex: peu d'incidents
critiques, beaucoup d'incidents mineurs — c'est le cas dans la vraie vie
aussi, on parle parfois de "pyramide de sévérité").

Le module est organisé en petites fonctions, chacune responsable d'une
seule colonne ou d'une seule règle métier. C'est plus facile à tester,
à lire et à réutiliser qu'un gros bloc de code unique.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
from faker import Faker


# ---------------------------------------------------------------------------
# Constantes de configuration du "monde" simulé
# ---------------------------------------------------------------------------
# Regrouper les constantes en haut du fichier permet de les ajuster
# facilement sans devoir relire toute la logique plus bas.

# Les 4 types d'incidents suivis, avec leur probabilité d'apparition.
# Le phishing est volontairement le plus fréquent : c'est le vecteur
# d'attaque initial le plus courant en entreprise (cf. rapports annuels
# Verizon DBIR, ENISA, etc.), suivi du malware.
TYPES_INCIDENT = ["phishing", "malware", "accès non autorisé", "déni de service", "autre"]
POIDS_TYPES_INCIDENT = [0.35, 0.25, 0.20, 0.10, 0.10]

# Les 4 niveaux de sévérité, avec leur probabilité d'apparition.
# On simule une "pyramide" : beaucoup d'incidents faibles/moyens,
# peu d'incidents critiques. C'est réaliste : si une équipe avait
# 40 % d'incidents critiques en continu, elle serait en crise permanente.
SEVERITES = ["faible", "moyenne", "élevée", "critique"]
POIDS_SEVERITES = [0.40, 0.35, 0.18, 0.07]

# Temps de résolution médian (en heures) attendu selon la sévérité.
# Plus la sévérité est élevée, plus la résolution est longue : un incident
# critique demande souvent une investigation approfondie, la coordination
# de plusieurs équipes (réseau, système, juridique...), alors qu'un
# incident faible peut être traité par une seule personne rapidement.
MEDIANE_HEURES_RESOLUTION = {
    "faible": 4,
    "moyenne": 12,
    "élevée": 48,
    "critique": 96,
}

# Dispersion (sigma) de la loi log-normale utilisée pour le temps de
# résolution. Une loi log-normale est utilisée (plutôt qu'une loi
# normale classique) car les temps de résolution, en pratique, ont une
# distribution asymétrique à droite : beaucoup de tickets résolus vite,
# mais une "longue traîne" de tickets qui prennent beaucoup plus de
# temps que la moyenne. Une loi normale autoriserait des valeurs
# négatives, ce qui n'a pas de sens pour une durée.
SIGMA_RESOLUTION = 0.7

# Systèmes affectés typiques, associés au type d'incident le plus
# probable pour ce système (corrélation réaliste : un DDoS touche
# rarement un poste de travail individuel, par exemple).
SYSTEMES_PAR_TYPE = {
    "phishing": ["Messagerie", "Portail webmail", "Poste de travail"],
    "malware": ["Poste de travail", "Serveur de fichiers", "Serveur applicatif"],
    "accès non autorisé": ["Active Directory", "VPN d'entreprise", "Application RH", "Base de données clients"],
    "déni de service": ["Site web public", "Serveur web", "Infrastructure réseau"],
    "autre": ["Poste de travail", "Serveur applicatif", "Application interne"],
}

# Fenêtre temporelle sur laquelle les incidents sont "ouverts" : les 365
# derniers jours. Simule un historique d'un an, suffisant pour observer
# une tendance hebdomadaire dans analysis.py.
JOURS_HISTORIQUE = 365


def generer_severites(n: int, rng: np.random.Generator) -> np.ndarray:
    """Tire aléatoirement n sévérités selon la distribution POIDS_SEVERITES.

    On utilise rng.choice plutôt que random.choices pour rester cohérent
    avec le reste du module, qui utilise numpy pour toutes les tirages
    aléatoires (permet un seul seed pour tout reproduire).
    """
    return rng.choice(SEVERITES, size=n, p=POIDS_SEVERITES)


def generer_types_incident(n: int, rng: np.random.Generator) -> np.ndarray:
    """Tire aléatoirement n types d'incidents selon POIDS_TYPES_INCIDENT."""
    return rng.choice(TYPES_INCIDENT, size=n, p=POIDS_TYPES_INCIDENT)


def generer_dates_ouverture(n: int, rng: np.random.Generator, aujourdhui: pd.Timestamp) -> pd.DatetimeIndex:
    """Tire n dates d'ouverture uniformément réparties sur les 365 derniers jours.

    Une distribution uniforme sur l'année est une simplification
    raisonnable pour un projet d'apprentissage : dans la réalité, il
    pourrait y avoir des pics saisonniers (ex: plus de phishing autour
    des fêtes), mais ce n'est pas nécessaire ici pour illustrer le
    pipeline d'analyse.
    """
    jours_avant = rng.integers(low=0, high=JOURS_HISTORIQUE, size=n)
    # On ajoute aussi une composante en heures/minutes pour éviter que
    # tous les tickets "tombent" exactement à minuit, ce qui ferait une
    # donnée trop artificielle.
    secondes_dans_journee = rng.integers(low=0, high=24 * 3600, size=n)
    deltas = pd.to_timedelta(jours_avant, unit="D") + pd.to_timedelta(secondes_dans_journee, unit="s")
    dates = aujourdhui - deltas
    # On arrondit à la minute : un vrai système de ticketing n'horodate
    # pas à la nanoseconde près, et ça évite un CSV inutilement "bruité".
    return dates.round("min")


def generer_systeme_affecte(types_incident: np.ndarray, rng: np.random.Generator, fake: Faker) -> list[str]:
    """Choisit un système affecté cohérent avec le type d'incident, et lui
    associe une étiquette d'inventaire (asset tag) générée par Faker.

    On utilise Faker ici pour simuler un identifiant d'actif informatique
    tel qu'on en trouverait dans un vrai inventaire (CMDB) d'entreprise,
    par exemple "Poste de travail (PC-4821)". Ça rend le jeu de données
    plus réaliste sans introduire de vraie donnée sensible : Faker ne
    fait que générer du texte plausible, pas des données réelles.
    """
    systemes = []
    for type_incident in types_incident:
        famille = rng.choice(SYSTEMES_PAR_TYPE[type_incident])
        tag_actif = fake.bothify(text="??-####").upper()
        systemes.append(f"{famille} ({tag_actif})")
    return systemes


def determiner_statut_et_resolution(
    dates_ouverture: pd.DatetimeIndex,
    severites: np.ndarray,
    rng: np.random.Generator,
    aujourdhui: pd.Timestamp,
) -> pd.DataFrame:
    """Détermine, pour chaque incident, son statut, sa date de résolution
    (si applicable) et son temps de résolution en heures.

    La logique est volontairement construite pour être réaliste plutôt
    que purement aléatoire :

    1. On tire un temps de résolution "potentiel" (combien de temps il
       aurait fallu pour résoudre ce ticket, selon sa sévérité).
    2. On calcule l'âge actuel du ticket (aujourd'hui - date d'ouverture).
    3. Si le ticket a eu assez de temps pour être résolu, on le marque
       "résolu" ou "fermé" (selon depuis quand il est résolu).
    4. Sinon, il reste "ouvert" (très récent) ou "en cours".
    5. On ajoute une petite probabilité qu'un ticket reste bloqué même
       après avoir eu assez de temps : ça simule le retard réel qu'on
       observe dans une vraie équipe (backlog, dépassement de SLA), et
       c'est justement ce que le module analysis.py devra détecter.
    """
    n = len(dates_ouverture)

    # Étape 1 : temps de résolution "potentiel" tiré d'une loi log-normale
    # dont la médiane dépend de la sévérité.
    medianes = np.array([MEDIANE_HEURES_RESOLUTION[s] for s in severites])
    # Pour une loi log-normale, le paramètre "mean" (mu) est le log de la
    # médiane souhaitée, car la médiane d'une log-normale vaut exp(mu).
    temps_potentiel = rng.lognormal(mean=np.log(medianes), sigma=SIGMA_RESOLUTION)

    # Étape 2 : âge du ticket en heures.
    age_heures = (aujourdhui - dates_ouverture).total_seconds() / 3600

    # Étape 3/4 : le ticket a-t-il eu assez de temps pour être résolu ?
    aurait_pu_etre_resolu = age_heures >= temps_potentiel

    # Étape 5 : 8 % des tickets qui "auraient pu" être résolus restent
    # bloqués (retard réel de traitement, SLA dépassé).
    reste_bloque = rng.random(n) < 0.08
    est_resolu = aurait_pu_etre_resolu & ~reste_bloque

    statuts = np.empty(n, dtype=object)
    dates_resolution = pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns]")
    temps_resolution_heures = np.full(n, np.nan)

    for i in range(n):
        if est_resolu[i]:
            date_resolution = (dates_ouverture[i] + pd.to_timedelta(temps_potentiel[i], unit="h")).round("min")
            dates_resolution.iloc[i] = date_resolution
            temps_resolution_heures[i] = round(temps_potentiel[i], 1)
            # Règle métier : un ticket résolu depuis plus de 5 jours est
            # considéré "fermé" (vérifié et archivé) ; sinon il est encore
            # "résolu" (résolution récente, en attente de clôture
            # formelle). Ça reflète un vrai workflow ITSM.
            jours_depuis_resolution = (aujourdhui - date_resolution).total_seconds() / 3600 / 24
            statuts[i] = "fermé" if jours_depuis_resolution > 5 else "résolu"
        else:
            # Ticket pas encore résolu : "ouvert" s'il est très récent
            # (moins de 24h), "en cours" sinon (déjà pris en charge).
            statuts[i] = "ouvert" if age_heures[i] < 24 else "en cours"

    return pd.DataFrame(
        {
            "statut": statuts,
            "date_resolution": dates_resolution.values,
            "temps_resolution_heures": temps_resolution_heures,
        }
    )


def generer_dataset(n_incidents: int = 200, seed: int = 42) -> pd.DataFrame:
    """Génère le DataFrame complet des incidents synthétiques.

    Le paramètre `seed` fixe la graine du générateur aléatoire : avec la
    même graine, on obtient toujours exactement le même jeu de données.
    C'est essentiel pour l'apprentissage (résultats reproductibles d'une
    exécution à l'autre) et pour le débogage.
    """
    rng = np.random.default_rng(seed)
    fake = Faker("fr_FR")
    fake.seed_instance(seed)

    aujourdhui = pd.Timestamp(dt.datetime.now().date())

    severites = generer_severites(n_incidents, rng)
    types_incident = generer_types_incident(n_incidents, rng)
    dates_ouverture = generer_dates_ouverture(n_incidents, rng, aujourdhui)
    systemes_affectes = generer_systeme_affecte(types_incident, rng, fake)
    df_statut = determiner_statut_et_resolution(dates_ouverture, severites, rng, aujourdhui)

    df = pd.DataFrame(
        {
            "id": [f"INC-{i + 1:04d}" for i in range(n_incidents)],
            "date_ouverture": dates_ouverture,
            "date_resolution": df_statut["date_resolution"].values,
            "type_incident": types_incident,
            "severite": severites,
            "statut": df_statut["statut"].values,
            "temps_resolution_heures": df_statut["temps_resolution_heures"].values,
            "systeme_affecte": systemes_affectes,
        }
    )

    # On trie par date d'ouverture : un vrai export de ticketing est
    # généralement chronologique, et ça rend le CSV plus lisible.
    df = df.sort_values("date_ouverture").reset_index(drop=True)

    return df


def sauvegarder_csv(df: pd.DataFrame, chemin: str) -> None:
    """Sauvegarde le DataFrame en CSV, encodé en UTF-8 (important pour les
    accents français) et sans la colonne d'index pandas (qui n'a pas de
    sens métier dans le fichier final).
    """
    df.to_csv(chemin, index=False, encoding="utf-8")
    print(f"[generate_data] {len(df)} incidents sauvegardés dans : {chemin}")


if __name__ == "__main__":
    # Permet d'exécuter ce module seul, en plus de l'appeler depuis
    # main.py : pratique pour tester rapidement pendant le développement.
    donnees = generer_dataset(n_incidents=200, seed=42)
    sauvegarder_csv(donnees, "data/incidents.csv")
    print(donnees.head(10))
    print("\nRépartition des statuts :")
    print(donnees["statut"].value_counts())
    print("\nRépartition des sévérités :")
    print(donnees["severite"].value_counts())
