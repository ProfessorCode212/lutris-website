# Generated by Django 2.2.12 on 2021-12-23 23:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0049_game_coverart'),
    ]

    operations = [
        migrations.AlterField(
            model_name='game',
            name='coverart',
            field=models.ImageField(blank=True, upload_to='igdb'),
        ),
    ]
